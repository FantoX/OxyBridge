import argparse
import signal
import time
from datetime import timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert

from oxybridge.config import settings
from oxybridge.db import now, transaction, uid
from oxybridge.engine import create_run, enqueue, execute, orchestrate
from oxybridge.graph import next_times
from oxybridge.models import (
    Attempt,
    Audit,
    AuthSession,
    DeadLetter,
    Heartbeat,
    NodeRun,
    Outbox,
    PasswordReset,
    RateLimit,
    Run,
    Schedule,
    Workflow,
    Workspace,
)
from oxybridge.telemetry import configure, log

stopping = False


def stop(*args):
    global stopping
    stopping = True


def heartbeat(db, name):
    statement = insert(Heartbeat).values(name=name, seen_at=now())
    db.execute(
        statement.on_conflict_do_update(
            index_elements=[Heartbeat.name], set_={"seen_at": statement.excluded.seen_at}
        )
    )


def dispatch_once(run_id=None):
    claim = uid()
    with transaction() as db:
        query = select(Outbox).where(
            Outbox.published_at.is_(None),
            Outbox.available_at <= now(),
            or_(Outbox.claimed_until.is_(None), Outbox.claimed_until < now()),
        )
        if run_id:
            query = query.where(Outbox.payload["run_id"].as_string() == run_id)
        row = db.scalar(
            query.order_by(Outbox.created_at).limit(1).with_for_update(skip_locked=True)
        )
        if not row:
            return False
        row.claim_token, row.claimed_until = claim, now() + timedelta(seconds=180)
        row.attempt_count += 1
        event_id, task, payload = row.id, row.task, row.payload
    error = None
    try:
        if task == "oxybridge.orchestrate":
            orchestrate(payload["run_id"])
        elif task == "oxybridge.execute":
            execute(payload["node_run_id"], "dispatcher")
        else:
            raise ValueError("Unsupported task")
    except Exception:
        error = "Execution delivery failed. Durable work will be retried."
        log("outbox.delivery_failed", outbox_id=event_id)
    with transaction() as db:
        row = db.scalar(select(Outbox).where(Outbox.id == event_id).with_for_update())
        if row.claim_token != claim:
            return True
        row.claim_token, row.claimed_until = None, None
        if error:
            row.last_error = error
            row.available_at = now() + timedelta(seconds=min(60, 2 ** min(row.attempt_count, 6)))
        else:
            row.published_at, row.last_error = now(), None
        heartbeat(db, "dispatcher")
    return True


def drain(run_id=None, budget=None):
    deadline = time.monotonic() + (budget or settings().execution_budget_seconds)
    count = 0
    while time.monotonic() < deadline and not stopping:
        if not dispatch_once(run_id):
            if not run_id:
                break
            with transaction() as db:
                due = db.scalar(
                    select(Outbox.available_at)
                    .where(
                        Outbox.published_at.is_(None),
                        Outbox.payload["run_id"].as_string() == run_id,
                        Outbox.claimed_until.is_(None),
                    )
                    .order_by(Outbox.available_at)
                    .limit(1)
                )
            wait = (due - now()).total_seconds() if due else None
            # Short retry waits fit inside one invocation; longer delays remain durable for a tick.
            if wait is None or wait > 5 or wait > deadline - time.monotonic():
                break
            time.sleep(min(1, max(0.05, wait)))
            continue
        count += 1
    return count


def schedule_once():
    with transaction() as db:
        schedules = db.scalars(
            select(Schedule)
            .where(Schedule.enabled.is_(True), Schedule.next_run_at <= now())
            .order_by(Schedule.next_run_at)
            .limit(50)
            .with_for_update(skip_locked=True)
        ).all()
        for schedule in schedules:
            workflow = db.scalar(
                select(Workflow).where(Workflow.id == schedule.workflow_id).with_for_update()
            )
            due = schedule.next_run_at
            # Coalesce missed occurrences into one run after downtime instead of flooding the queue.
            schedule.next_run_at = next_times(schedule.cron, schedule.timezone, now(), 1)[0]
            if workflow and workflow.status == "ACTIVE":
                create_run(
                    db,
                    workflow,
                    {"scheduled_at": due.isoformat(), "timezone": schedule.timezone},
                    "schedule",
                    f"schedule:{schedule.id}:{due.isoformat()}",
                )
                schedule.last_run_at = now()
        heartbeat(db, "scheduler")


def recover_once():
    with transaction() as db:
        expired = db.scalars(
            select(NodeRun)
            .where(NodeRun.status == "RUNNING", NodeRun.lease_until < now())
            .limit(50)
            .with_for_update(skip_locked=True)
        ).all()
        for node in expired:
            attempt = db.scalar(
                select(Attempt).where(
                    Attempt.node_run_id == node.id, Attempt.number == node.attempt
                )
            )
            if attempt:
                attempt.status, attempt.error, attempt.finished_at = (
                    "FAILED",
                    "Worker lease expired; delivery may have completed an external effect.",
                    now(),
                )
            # shortcut: crash redelivery is bounded at 10, use node-specific crash policies if required.
            if node.attempt >= 10:
                node.status, node.error_code, node.error = (
                    "FAILED",
                    "WORKER_LOST",
                    "Worker delivery failed repeatedly.",
                )
                enqueue(db, "oxybridge.orchestrate", {"run_id": node.run_id})
            else:
                node.status, node.next_attempt_at, node.claim_token = "QUEUED", now(), None
                enqueue(db, "oxybridge.execute", {"node_run_id": node.id}, node.queue)
        # Reconcile a delivery that returned without completing its node claim.
        pending = db.scalars(
            select(NodeRun)
            .where(
                NodeRun.status.in_(["QUEUED", "RETRY_WAIT"]),
                NodeRun.next_attempt_at < now() - timedelta(seconds=30),
            )
            .limit(50)
            .with_for_update(skip_locked=True)
        ).all()
        for node in pending:
            node.next_attempt_at = now()
            enqueue(db, "oxybridge.execute", {"node_run_id": node.id}, node.queue)
        runs = db.scalars(
            select(Run)
            .where(Run.status.in_(["QUEUED", "RUNNING", "CANCEL_REQUESTED"]))
            .order_by(Run.created_at)
            .limit(200)
        ).all()
        for run in runs:
            if (now() - run.created_at).total_seconds() > 30:
                enqueue(db, "oxybridge.orchestrate", {"run_id": run.id})
        heartbeat(db, "recovery")


def retention_once():
    with transaction() as db:
        for workspace in db.scalars(select(Workspace)).all():
            runs = db.scalars(
                select(Run)
                .where(
                    Run.workspace_id == workspace.id,
                    Run.status.in_(["SUCCEEDED", "CANCELLED", "FAILED", "TIMED_OUT"]),
                    Run.created_at < now() - timedelta(days=workspace.retention_days),
                )
                .limit(100)
            ).all()
            for run in runs:
                dead = db.scalar(select(DeadLetter).where(DeadLetter.run_id == run.id))
                if dead and not dead.resolved_at:
                    continue
                if db.scalar(select(Run.id).where(Run.recovery_of == run.id).limit(1)):
                    continue
                links = db.scalars(
                    select(DeadLetter).where(DeadLetter.recovery_run_id == run.id)
                ).all()
                if any(not link.resolved_at for link in links):
                    continue
                for link in links:
                    link.recovery_run_id = None
                db.flush()
                node_ids = select(NodeRun.id).where(NodeRun.run_id == run.id)
                db.execute(delete(Attempt).where(Attempt.node_run_id.in_(node_ids)))
                db.execute(delete(DeadLetter).where(DeadLetter.run_id == run.id))
                db.execute(delete(NodeRun).where(NodeRun.run_id == run.id))
                db.delete(run)
        payload_runs = db.scalars(
            select(Run)
            .where(
                Run.created_at < now() - timedelta(days=settings().payload_retention_days),
                Run.status.in_(["SUCCEEDED", "CANCELLED"]),
            )
            .limit(100)
        ).all()
        for run in payload_runs:
            run.trigger_payload, run.encrypted_payload = {"retained": False}, None
            for node in db.scalars(select(NodeRun).where(NodeRun.run_id == run.id)).all():
                node.input_data, node.output_data, node.encrypted_output = None, None, None
        old = now() - timedelta(days=settings().audit_retention_days)
        ids = select(Audit.id).where(Audit.created_at < old).limit(500)
        db.execute(delete(Audit).where(Audit.id.in_(ids)))
        sent = select(Outbox.id).where(Outbox.published_at < now() - timedelta(days=7)).limit(500)
        db.execute(delete(Outbox).where(Outbox.id.in_(sent)))
        db.execute(delete(AuthSession).where(AuthSession.refresh_expires_at < now()))
        db.execute(delete(PasswordReset).where(PasswordReset.expires_at < now()))
        db.execute(delete(RateLimit).where(RateLimit.expires_at < now()))
        heartbeat(db, "retention")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("service", choices=["dispatcher", "scheduler"])
    args = parser.parse_args()
    configure(args.service)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    last_recovery, last_retention = 0, 0
    while not stopping:
        try:
            if args.service == "dispatcher":
                drain(budget=5)
                if time.monotonic() - last_recovery > 10:
                    recover_once()
                    last_recovery = time.monotonic()
            else:
                schedule_once()
                if time.monotonic() - last_retention > 3600:
                    retention_once()
                    last_retention = time.monotonic()
        except Exception:
            log("service.iteration_failed", service=args.service)
        time.sleep(0.5 if args.service == "dispatcher" else 2)


if __name__ == "__main__":
    main()
