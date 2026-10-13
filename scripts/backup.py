"""Create a private PostgreSQL dump, or verify it in a new disposable local database."""

import argparse
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from oxybridge.config import settings
from oxybridge.security import decrypt


def pg_environment(url):
    return {
        **os.environ,
        "PGHOST": url.host or "localhost",
        "PGPORT": str(url.port or 5432),
        "PGDATABASE": url.database,
        "PGUSER": url.username,
        "PGPASSWORD": url.password or "",
        "PGSSLMODE": url.query.get("sslmode", "prefer"),
        "PGCONNECT_TIMEOUT": "15",
    }


def pg_tool(name):
    binary = shutil.which(name) or str(
        Path(os.environ.get("PG_BIN", "C:/Program Files/PostgreSQL/18/bin")) / (name + ".exe")
    )
    if not Path(binary).is_file():
        raise SystemExit(f"Install PostgreSQL client tools and set PG_BIN or PATH for {name}.")
    return binary


def run_tool(name, arguments, url):
    result = subprocess.run(
        [pg_tool(name), *arguments], env=pg_environment(url), capture_output=True, text=True
    )
    if result.returncode:
        raise SystemExit(
            f"{name} failed; the database was not verified. Check client version and access."
        )


def restore_check(dump, target):
    if target.host not in {"127.0.0.1", "localhost"} or not target.database.endswith("_test"):
        raise SystemExit("Restore checks require a local disposable database ending in _test.")
    env = pg_environment(target)
    connect = dict(
        host=env["PGHOST"], port=env["PGPORT"], user=env["PGUSER"], password=env["PGPASSWORD"]
    )
    with psycopg.connect(**connect, dbname="postgres", autocommit=True) as db:
        if db.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (target.database,)
        ).fetchone():
            raise SystemExit("The restore database already exists. Use a fresh database name.")
        db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target.database)))
    run_tool(
        "pg_restore",
        ["--exit-on-error", "--no-owner", "--no-acl", "-d", target.database, str(dump)],
        target,
    )
    with psycopg.connect(**connect, dbname=target.database) as db:
        migration = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert migration == "0002", "Unexpected migration version"
        counts = {
            table: db.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
            ).fetchone()[0]
            for table in ("users", "workflows", "workflow_versions", "workflow_runs", "connections")
        }
        assert counts["users"] and counts["workflow_versions"], "Backup lacks application data"
        for (ciphertext,) in db.execute("SELECT encrypted_secret FROM connections"):
            assert isinstance(decrypt(ciphertext), dict), "Credential decryption failed"
    print(f"Restore verified at migration {migration}; row counts: {counts}.")
    print("The restored database is left in place for inspection. No workflows were dispatched.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["backup", "restore-check"])
    parser.add_argument("--dump", type=Path)
    args = parser.parse_args()
    if args.command == "restore-check":
        if not args.dump or not args.dump.is_file() or not os.environ.get("RESTORE_DATABASE_URL"):
            parser.error(
                "Supply --dump and RESTORE_DATABASE_URL pointing to a fresh local database."
            )
        restore_check(args.dump, make_url(os.environ["RESTORE_DATABASE_URL"]))
        return
    dump = args.dump or Path(".local/backups") / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".dump"
    )
    if dump.exists():
        parser.error("The dump already exists; it was not overwritten.")
    dump.parent.mkdir(parents=True, exist_ok=True)
    run_tool(
        "pg_dump",
        ["--format=custom", "--no-owner", "--no-acl", "--file", str(dump)],
        make_url(settings().database_url),
    )
    assert dump.stat().st_size > 0, "Empty backup"
    print(f"Created private backup: {dump}")


if __name__ == "__main__":
    main()
