import argparse
import base64
import getpass
import json
import os
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="OxyBridge instance administration")
    parser.add_argument("command", choices=["keys", "init-config", "seed", "reset-password"])
    parser.add_argument("--email", default="owner@oxybridge.local")
    args = parser.parse_args()
    if args.command in {"keys", "init-config"}:
        values = {
            "SECRET_KEY": secrets.token_urlsafe(48),
            "ENCRYPTION_MASTER_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            "CRON_SECRET": secrets.token_urlsafe(48),
            "SETUP_TOKEN": secrets.token_urlsafe(48),
        }
        if args.command == "keys":
            print("\n".join(f"{k}={v}" for k, v in values.items()))
        else:
            path = Path(".env")
            if path.exists():
                parser.error(".env already exists; it was not overwritten")
            example = Path(".env.example").read_text()
            for key, value in values.items():
                example = example.replace(key + "=\n", key + "=" + value + "\n")
            path.write_text(example)
            print("Created .env with new instance keys. Configure DATABASE_URL before migrating.")
        return
    from sqlalchemy import select

    from oxybridge.db import transaction, uid
    from oxybridge.models import Member, Organization, User, Version, Workflow, Workspace
    from oxybridge.security import content_hash, passwords

    if args.command == "reset-password":
        password = getpass.getpass("New password (12+ characters): ")
        if len(password) < 12:
            parser.error("Use at least 12 characters")
        with transaction() as db:
            user = db.scalar(select(User).where(User.email == args.email.lower()))
            if not user:
                parser.error("User not found")
            user.password_hash = passwords.hash(password)
            from sqlalchemy import delete

            from oxybridge.models import AuthSession

            db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        print("Password updated and sessions revoked.")
        return
    from oxybridge.config import settings

    if settings().app_env in {"staging", "production"}:
        parser.error("Demo seeding is disabled in production; use the protected setup screen")
    from oxybridge.templates import templates

    with transaction() as db:
        if db.scalar(select(User.id).limit(1)):
            print("An owner already exists; no seed data was changed.")
            return
        password = os.environ.get("OXYBRIDGE_SEED_PASSWORD") or secrets.token_urlsafe(18)
        if len(password) < 12:
            parser.error("Seed password must contain at least 12 characters")
        user = User(
            id=uid(),
            email=args.email,
            display_name="Workspace owner",
            password_hash=passwords.hash(password),
        )
        organization = Organization(id=uid(), name="OxyBridge workspace", slug="oxybridge")
        db.add_all([user, organization])
        db.flush()
        workspace = Workspace(
            id=uid(),
            organization_id=organization.id,
            name="Personal workspace",
            environment="development",
        )
        db.add_all(
            [workspace, Member(organization_id=organization.id, user_id=user.id, role="owner")]
        )
        db.flush()
        for template in templates():
            workflow = Workflow(
                id=uid(),
                workspace_id=workspace.id,
                name=template["name"],
                description=template["description"],
                definition=template["definition"],
                created_by=user.id,
            )
            db.add(workflow)
            db.flush()
            if template["id"] == "order-routing":
                version = Version(
                    id=uid(),
                    workflow_id=workflow.id,
                    number=1,
                    definition=template["definition"],
                    definition_hash=content_hash(template["definition"]),
                    published_by=user.id,
                )
                db.add(version)
                db.flush()
                workflow.active_version_id, workflow.status = version.id, "ACTIVE"
        credentials = {"email": args.email, "password": password, "url": settings().app_base_url}
        Path(".local").mkdir(exist_ok=True)
        Path(".local/login.json").write_text(json.dumps(credentials, indent=2))
    print(
        "Seeded the workspace and templates. Local login details are in .local/login.json (git ignored)."
    )


if __name__ == "__main__":
    main()
