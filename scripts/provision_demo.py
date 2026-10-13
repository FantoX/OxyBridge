"""Provision the fulfillment demo using a PostgreSQL role restricted to its own schema."""

import json
import secrets
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy import select
from sqlalchemy.engine import make_url

from oxybridge.api import publish_version
from oxybridge.auth import Principal, audit
from oxybridge.config import settings
from oxybridge.db import now, transaction, uid
from oxybridge.models import Connection, User, Workflow, Workspace
from oxybridge.nodes import postgres_query
from oxybridge.security import encrypt
from oxybridge.templates import order_template, routing_template


def main():
    url = make_url(settings().database_url)
    with transaction() as db:
        workspace = db.scalar(select(Workspace).order_by(Workspace.created_at).limit(1))
        owner = db.scalar(select(User).order_by(User.created_at).limit(1))
        if not workspace or not owner:
            raise SystemExit("Create the instance owner before provisioning the demo.")
        existing = db.scalar(
            select(Connection).where(
                Connection.workspace_id == workspace.id, Connection.name == "Order demo database"
            )
        )
        if existing:
            print(
                "The demo database connection already exists; no credentials or workflows were changed."
            )
            return
        schema = "demo_" + workspace.id.replace("-", "")[:12]
        role = "oxybridge_" + schema
        password = secrets.token_urlsafe(32)
        with psycopg.connect(
            host=url.host,
            port=url.port or 5432,
            dbname=url.database,
            user=url.username,
            password=url.password,
            **dict(url.query),
        ) as root:
            with root.cursor() as cursor:
                cursor.execute(
                    sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema))
                )
                cursor.execute(
                    sql.SQL(
                        "CREATE TABLE IF NOT EXISTS {}.orders (order_id text PRIMARY KEY, total numeric NOT NULL, priority text NOT NULL)"
                    ).format(sql.Identifier(schema))
                )
                cursor.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {}"
                    ).format(sql.Identifier(role), sql.Literal(password))
                )
                cursor.execute(
                    sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                        sql.Identifier(url.database), sql.Identifier(role)
                    )
                )
                cursor.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                        sql.Identifier(schema), sql.Identifier(role)
                    )
                )
                cursor.execute(
                    sql.SQL("GRANT SELECT, INSERT, UPDATE ON {}.orders TO {}").format(
                        sql.Identifier(schema), sql.Identifier(role)
                    )
                )
        credential = {
            "host": url.host,
            "port": url.port or 5432,
            "database": url.database,
            "username": role,
            "password": password,
            "sslmode": "verify-full",
        }
        check = postgres_query({"query": "SELECT 1 AS connected"}, {}, credential)
        assert check["rows"] == [{"connected": 1}]
        permission = postgres_query(
            {
                "query": "SELECT has_table_privilege(current_user, 'public.users', 'SELECT') AS allowed"
            },
            {},
            credential,
        )
        assert permission["rows"] == [{"allowed": False}], (
            "The demo role must not be able to read application users"
        )
        connection = Connection(
            id=uid(),
            workspace_id=workspace.id,
            name="Order demo database",
            type="postgres",
            encrypted_secret=encrypt(credential),
            allow_writes=True,
            tested_at=now(),
            test_status="VALID",
        )
        db.add(connection)
        db.flush()
        for name, definition in [
            ("Order routing", routing_template()),
            ("Order Fulfillment Demo", order_template()),
        ]:
            workflow = db.scalar(
                select(Workflow)
                .where(Workflow.workspace_id == workspace.id, Workflow.name == name)
                .with_for_update()
            )
            if workflow and workflow.revision != 1:
                print(f"Preserved existing edits to {name}.")
                continue
            if name == "Order Fulfillment Demo":
                for node in definition["nodes"]:
                    if node["type"] in {"http", "callback"}:
                        node["config"]["url"] = "https://postman-echo.com/post"
                        node["label"] += " (echo demo)"
                    if node["type"] == "postgres":
                        node["config"].update(
                            connection_id=connection.id,
                            query=f'INSERT INTO "{schema}".orders (order_id, total, priority) VALUES (%(order_id)s, %(total)s, %(priority)s) ON CONFLICT (order_id) DO UPDATE SET total = EXCLUDED.total, priority = EXCLUDED.priority RETURNING order_id, total, priority',
                            parameters={
                                "order_id": "{{ trigger.body.order_id }}",
                                "total": "{{ trigger.body.total }}",
                                "priority": "{{ vars.priority }}",
                            },
                        )
            if not workflow:
                workflow = Workflow(
                    id=uid(),
                    workspace_id=workspace.id,
                    name=name,
                    created_by=owner.id,
                    definition=definition,
                )
                db.add(workflow)
                db.flush()
            workflow.definition = definition
            workflow.revision += 1
            workflow.updated_at = now()
            if name == "Order Fulfillment Demo":
                workflow.description = "A working demo: validate and route an order, call a public echo API, store it in an isolated PostgreSQL schema, and send an echo callback. Replace the echo URLs with your providers."
            version = publish_version(db, workflow, owner.id)
            workflow.active_version_id, workflow.status = version.id, "ACTIVE"
            audit(db, Principal(owner.id, workspace, "owner"), "demo.provisioned", workflow.id)
        Path(".local").mkdir(exist_ok=True)
        Path(".local/demo.json").write_text(
            json.dumps({"schema": schema, "connection_id": connection.id})
        )
    print("Demo role verified: can connect with verified TLS, cannot read application users.")
    print("Published routing and fulfillment demos with encrypted, scoped database credentials.")


if __name__ == "__main__":
    main()
