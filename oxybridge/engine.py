import json
import random
from datetime import timedelta

from opentelemetry.propagate import extract, inject
from sqlalchemy import select
from sqlalchemy.orm import Session

from oxybridge.config import settings
from oxybridge.db import now, transaction, uid
from oxybridge.graph import NODE_TERMINAL, TERMINAL, NodeError, resolve
from oxybridge.models import (
    Attempt,
    Connection,
    DeadLetter,
    NodeRun,
    Outbox,
    Run,
    Version,
    Workspace,
)
from oxybridge.nodes import execute_node
from oxybridge.security import (
    content_hash,
    decrypt,
    encrypt,
    redact,
    secret_values,
    sensitive_values,
)
from oxybridge.telemetry import log, tracer

QUEUES = {"http": "http", "callback": "callbacks", "postgres": "database"}
RUN_TRANSITIONS = {
    "QUEUED": {"RUNNING", "CANCELLED", "TIMED_OUT"},
    "RUNNING": {"SUCCEEDED", "FAILED", "CANCEL_REQUESTED", "TIMED_OUT"},
    "CANCEL_REQUESTED": {"CANCELLED", "TIMED_OUT"},
}


def transition(run, target):
    if target not in RUN_TRANSITIONS.get(run.status, set()):
        raise ValueError(f"Invalid run transition {run.status} -> {target}")
    run.status = target
    if target in TERMINAL:
        run.finished_at = now()
        run.duration_ms = int(
            (run.finished_at - (run.started_at or run.created_at)).total_seconds() * 1000
        )


def enqueue(db, task, payload, queue="orchestrator", available_at=None):
    if "node_run_id" in payload and "run_id" not in payload:
        node = db.get(NodeRun, payload["node_run_id"])
        payload = {**payload, "run_id": node.run_id}
    db.add(Outbox(task=task, payload=payload, queue=queue, available_at=available_at or now()))


def create_run(
    db: Session,
    workflow,
    payload,
    trigger_type="manual",
    idempotency_key=None,
    version_id=None,
    recovery_of=None,
    trigger_metadata=None,
):
    fingerprint = content_hash(
        {"payload": payload, "version_id": version_id or workflow.active_version_id}
    )
    if idempotency_key:
        existing = db.scalar(
            select(Run).where(
                Run.workflow_id == workflow.id, Run.idempotency_key == idempotency_key
            )
        )
        if existing:
            if existing.request_hash != fingerprint:
                raise NodeError(
                    "IDEMPOTENCY_CONFLICT",
                    "This idempotency key was already used with different input or version.",
                )
            return existing
    if workflow.status != "ACTIVE" and not version_id:
        raise NodeError("WORKFLOW_DISABLED", "Publish and enable this workflow before running it.")
    version = db.get(Version, version_id or workflow.active_version_id)
    if not version or version.workflow_id != workflow.id:
        raise NodeError("WORKFLOW_INVALID", "This workflow has no executable version.")
    trace_context = {}
    inject(trace_context)
    trace_context["trigger"] = redact(trigger_metadata or {})
    run = Run(
        id=uid(),
        workspace_id=workflow.workspace_id,
        workflow_id=workflow.id,
        version_id=version.id,
        trigger_type=trigger_type,
        idempotency_key=idempotency_key,
        request_hash=fingerprint,
        trigger_payload=redact(payload),
        encrypted_payload=encrypt(payload),
        recovery_of=recovery_of,
        trace_context=trace_context,
    )
    db.add(run)
    db.flush()
    for node in version.definition["nodes"]:
        db.add(
            NodeRun(
                id=uid(),
                run_id=run.id,
                node_id=node["id"],
                node_type=node["type"],
                label=node.get("label", node["type"]),
                queue=QUEUES.get(node["type"], "default"),
            )
        )
    enqueue(db, "oxybridge.orchestrate", {"run_id": run.id})
    return run


def retry_delay(policy, attempt):
    base = min(
        float(policy.get("max_delay", 120)),
        float(policy.get("initial_delay", 2))
        * float(policy.get("multiplier", 2)) ** max(0, attempt - 1),
    )
    return random.uniform(base * 0.5, base) if policy.get("jitter", True) else base


def orchestrate(run_id):
    with transaction() as db:
        run = db.scalar(select(Run).where(Run.id == run_id).with_for_update())
        if not run or run.status in TERMINAL:
            return
        if run.status == "QUEUED":
            transition(run, "RUNNING")
            run.started_at = now()
        node_runs = db.scalars(select(NodeRun).where(NodeRun.run_id == run.id)).all()
        if (now() - run.created_at).total_seconds() > settings().run_max_seconds:
            transition(run, "TIMED_OUT")
            run.error_code, run.error = (
                "RUN_TIMED_OUT",
                "The workflow exceeded its maximum duration. In-flight external effects may still complete.",
            )
            for node in node_runs:
                if node.status not in NODE_TERMINAL and node.status != "RUNNING":
                    node.status = "CANCELLED"
            db.add(DeadLetter(workspace_id=run.workspace_id, run_id=run.id, reason=run.error))
            return
        if run.status == "CANCEL_REQUESTED":
            for node in node_runs:
                if node.status not in NODE_TERMINAL and node.status != "RUNNING":
                    node.status = "CANCELLED"
            if not any(n.status == "RUNNING" for n in node_runs):
                transition(run, "CANCELLED")
            return
        definition = db.get(Version, run.version_id).definition
        by_id = {n.node_id: n for n in node_runs}
        incoming = {n.node_id: [] for n in node_runs}
        for edge in definition["edges"]:
            incoming[edge["target"]].append(edge)
        # A merge waits for every parent to finish, then accepts any successful selected branch.
        changed = True
        while changed:
            changed = False
            for node in node_runs:
                if node.status != "PENDING":
                    continue
                parents = incoming[node.node_id]
                if any(by_id[e["source"]].status not in NODE_TERMINAL for e in parents):
                    continue
                eligible = not parents or any(
                    by_id[e["source"]].status == "SUCCEEDED"
                    and (e.get("sourceHandle") in {None, "success", by_id[e["source"]].branch})
                    for e in parents
                )
                if not eligible:
                    node.status = "SKIPPED"
                    changed = True
                    continue
                node.status = "QUEUED"
                node.next_attempt_at = now()
                enqueue(db, "oxybridge.execute", {"node_run_id": node.id}, node.queue)
        failed = next((n for n in node_runs if n.status == "FAILED"), None)
        if all(n.status in NODE_TERMINAL for n in node_runs):
            if failed:
                transition(run, "FAILED")
                run.error_code, run.error = failed.error_code, failed.error
                db.add(
                    DeadLetter(
                        workspace_id=run.workspace_id,
                        run_id=run.id,
                        node_run_id=failed.id,
                        reason=failed.error or "Node failed.",
                    )
                )
            else:
                transition(run, "SUCCEEDED")
                if run.recovery_of:
                    item = db.scalar(select(DeadLetter).where(DeadLetter.run_id == run.recovery_of))
                    if item:
                        item.resolved_at, item.recovery_run_id = now(), run.id
            log(
                "run.finished",
                workflow_run_id=run.id,
                workflow_id=run.workflow_id,
                status=run.status,
                duration_ms=run.duration_ms,
            )


def execute(node_run_id, worker_id="local"):
    claim = uid()
    with transaction() as db:
        ref = db.get(NodeRun, node_run_id)
        if not ref:
            return
        run = db.scalar(select(Run).where(Run.id == ref.run_id).with_for_update())
        # Refresh the cached reference after waiting for another delivery's lock.
        node_run = db.scalar(
            select(NodeRun)
            .where(NodeRun.id == node_run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            run.status in TERMINAL
            or run.status == "CANCEL_REQUESTED"
            or node_run.status not in {"QUEUED", "RETRY_WAIT"}
        ):
            return
        if node_run.next_attempt_at and node_run.next_attempt_at > now():
            return
        if (now() - run.created_at).total_seconds() > settings().run_max_seconds:
            enqueue(db, "oxybridge.orchestrate", {"run_id": run.id})
            return
        definition = db.get(Version, run.version_id).definition
        node = next(n for n in definition["nodes"] if n["id"] == node_run.node_id)
        config = node.get("config", {})
        if node["type"] == "delay" and node_run.attempt == 0 and not node_run.started_at:
            node_run.started_at = now()
            node_run.status = "RETRY_WAIT"
            node_run.next_attempt_at = now() + timedelta(seconds=float(config["seconds"]))
            enqueue(
                db,
                "oxybridge.execute",
                {"node_run_id": node_run.id},
                node_run.queue,
                node_run.next_attempt_at,
            )
            return
        node_run.status, node_run.claim_token = "RUNNING", claim
        node_run.lease_until = now() + timedelta(seconds=180)
        node_run.started_at = node_run.started_at or now()
        node_run.attempt += 1
        node_run.worker_id = worker_id
        attempt = Attempt(
            id=uid(), node_run_id=node_run.id, number=node_run.attempt, status="RUNNING"
        )
        db.add(attempt)
        attempt_id = attempt.id
        ancestors, stack = set(), [node_run.node_id]
        while stack:
            child = stack.pop()
            for edge in definition["edges"]:
                if edge["target"] == child and edge["source"] not in ancestors:
                    ancestors.add(edge["source"])
                    stack.append(edge["source"])
        all_nodes = db.scalars(
            select(NodeRun).where(
                NodeRun.run_id == run.id,
                NodeRun.status == "SUCCEEDED",
                NodeRun.node_id.in_(ancestors),
            )
        ).all()
        outputs = {
            n.node_id: {
                "status": n.status,
                "output": decrypt(n.encrypted_output) if n.encrypted_output else n.output_data,
            }
            for n in all_nodes
        }
        for n in definition["nodes"]:
            if n.get("alias") and n["id"] in outputs:
                outputs[n["alias"]] = outputs[n["id"]]
        workspace = db.get(Workspace, run.workspace_id)
        payload = decrypt(run.encrypted_payload) if run.encrypted_payload else run.trigger_payload
        context = {
            "run": {
                "id": run.id,
                "node_id": node_run.node_id,
                "started_at": run.started_at.isoformat(),
            },
            "trigger": {
                "body": payload,
                "headers": run.trace_context.get("trigger", {}).get("headers", {}),
                "query": run.trace_context.get("trigger", {}).get("query", {}),
            },
            "nodes": outputs,
            "env": {"workspace": workspace.environment},
            "vars": {},
        }
        # Set nodes expose their mapping as vars; explicit node references remain unambiguous at merges.
        for n in definition["nodes"]:
            if n["type"] == "set" and n["id"] in outputs:
                context["vars"].update(outputs[n["id"]]["output"])
        secrets_to_hide, credential, connection = sensitive_values(payload), None, None
        credential_secrets = []
        used_connections = {
            n.get("config", {}).get("connection_id")
            for n in definition["nodes"]
            if n["id"] in ancestors or n["id"] == node_run.node_id
        }
        for used in db.scalars(
            select(Connection).where(
                Connection.workspace_id == run.workspace_id,
                Connection.id.in_([i for i in used_connections if i]),
            )
        ).all():
            value = decrypt(used.encrypted_secret)
            secrets_to_hide.extend(secret_values(value))
            credential_secrets.extend(sensitive_values(value))
            if used.type == "basic":
                credential_secrets.extend(secret_values(value)[-1:])
        connection_id = config.get("connection_id")
        if connection_id:
            connection = db.get(Connection, connection_id)
            if connection and connection.workspace_id == run.workspace_id and connection.enabled:
                credential = decrypt(connection.encrypted_secret)
                secrets_to_hide.extend(secret_values(credential))
                connection.last_used_at = now()
            else:
                connection = None
        node_run.input_data = redact(context["trigger"]["body"], secrets_to_hide)
        trace_context = run.trace_context
        number = node_run.attempt
    started = now()
    try:
        node_input = resolve(config, context)
    except NodeError:
        node_input = {
            "configuration": config,
            "note": "An expression was unavailable before execution.",
        }
    error, output, branch = None, None, None
    with tracer.start_as_current_span(
        "node." + node["type"],
        context=extract(trace_context),
        attributes={
            "workflow.run_id": run.id,
            "workflow.node_id": node_run.node_id,
            "workflow.attempt": number,
        },
    ):
        try:
            if connection_id and not credential:
                raise NodeError(
                    "CREDENTIAL_UNAVAILABLE",
                    "The configured connection is disabled or unavailable.",
                )
            output, branch = execute_node(node, context, credential, connection)
            if len(json.dumps(output, default=str).encode()) > 524288:
                raise NodeError(
                    "NODE_OUTPUT_TOO_LARGE", "The node output exceeds the 512 KB storage limit."
                )
            if (
                node["type"] == "validate"
                and branch == "invalid"
                and not any(
                    e["source"] == node["id"] and e.get("sourceHandle") == "invalid"
                    for e in definition["edges"]
                )
            ):
                raise NodeError(
                    "PAYLOAD_INVALID", "JSON validation failed; no invalid branch is connected."
                )
        except NodeError as caught:
            error = caught
        except Exception:
            error = NodeError(
                "NODE_EXECUTION_FAILED",
                "Node execution failed. Check its configuration and connection.",
            )
    finished = now()
    with transaction() as db:
        locked_run = db.scalar(select(Run).where(Run.id == run.id).with_for_update())
        nr = db.scalar(select(NodeRun).where(NodeRun.id == node_run_id).with_for_update())
        if nr.claim_token != claim:
            return
        attempt = db.get(Attempt, attempt_id)
        nr.lease_until, nr.claim_token = None, None
        nr.duration_ms = int((finished - nr.started_at).total_seconds() * 1000)
        nr.input_data = redact(
            {"trigger": context["trigger"], "configuration": node_input}, secrets_to_hide
        )
        attempt.duration_ms = int((finished - started).total_seconds() * 1000)
        attempt.finished_at = finished
        if error:
            nr.error_code, nr.error = error.code, redact(str(error), secrets_to_hide)
            attempt.status, attempt.error, attempt.http_status = (
                "FAILED",
                nr.error,
                error.http_status,
            )
            policy = config.get("retry", {})
            if (
                error.retryable
                and number < int(policy.get("max_attempts", 3))
                and locked_run.status == "RUNNING"
            ):
                nr.status = "RETRY_WAIT"
                nr.next_attempt_at = finished + timedelta(seconds=retry_delay(policy, number))
                enqueue(
                    db, "oxybridge.execute", {"node_run_id": nr.id}, nr.queue, nr.next_attempt_at
                )
            else:
                nr.status, nr.finished_at = "FAILED", finished
        else:
            nr.status, nr.finished_at, nr.branch = "SUCCEEDED", finished, branch
            nr.output_data = redact(output, secrets_to_hide)
            nr.encrypted_output = encrypt(redact(output, credential_secrets, mask_fields=False))
            nr.error, nr.error_code = None, None
            attempt.status = "SUCCEEDED"
        enqueue(db, "oxybridge.orchestrate", {"run_id": run.id})
        log(
            "node.finished",
            workflow_run_id=run.id,
            node_id=nr.node_id,
            node_run_id=nr.id,
            attempt=number,
            status=nr.status,
            duration_ms=attempt.duration_ms,
            worker_id=worker_id,
        )
