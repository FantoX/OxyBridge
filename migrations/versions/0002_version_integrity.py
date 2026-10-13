"""Protect immutable versions and enforce the active version reference."""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    op.create_foreign_key(
        "fk_workflow_active_version",
        "workflows",
        "workflow_versions",
        ["active_version_id"],
        ["id"],
    )
    op.execute("""
        CREATE OR REPLACE FUNCTION reject_version_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'Workflow versions are immutable; publish a new version';
        END;
        $$;
        CREATE TRIGGER workflow_versions_immutable BEFORE UPDATE OR DELETE ON workflow_versions
        FOR EACH ROW EXECUTE FUNCTION reject_version_mutation();
    """)


def downgrade():
    op.execute("DROP TRIGGER workflow_versions_immutable ON workflow_versions")
    op.execute("DROP FUNCTION reject_version_mutation()")
    op.drop_constraint("fk_workflow_active_version", "workflows", type_="foreignkey")
