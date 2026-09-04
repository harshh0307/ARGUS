"""snapshot_content_and_pointers

Move spec snapshots into the database and split named pointers into their own
table.

Before this revision, snapshot bodies lived on each process's local disk under
``data/snapshots`` and the ``spec_snapshots`` table held only a digest. That
meant api/worker/beat each kept a private copy, nothing survived a restart, and
progressive-baseline vendors could never produce a diff across processes.

``spec_pointers`` replaces the ``latest.json`` / ``<label>.json`` files. Keeping
pointers in their own rows is what stops pinning a baseline from clobbering the
latest pointer and discarding its ETag.

Revision ID: a9bec9bb0b7d
Revises: cd7a0398601e
Create Date: 2026-09-03 19:23:40.222725

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a9bec9bb0b7d'
down_revision: str | None = 'cd7a0398601e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'spec_pointers',
        sa.Column('vendor_slug', sa.String(length=64), nullable=False),
        sa.Column('label', sa.String(length=32), nullable=False),
        sa.Column('digest', sa.String(length=16), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['vendor_slug'], ['vendors.slug']),
        sa.PrimaryKeyConstraint('vendor_slug', 'label'),
    )

    # spec_format is NOT NULL in the model. Autogenerate emitted it without a
    # server default, which fails on any table that already has rows: add it
    # nullable, backfill, then enforce.
    op.add_column(
        'spec_snapshots',
        sa.Column('spec_format', sa.String(length=8), nullable=True),
    )
    op.execute("UPDATE spec_snapshots SET spec_format = 'json' WHERE spec_format IS NULL")

    op.add_column('spec_snapshots', sa.Column('content', sa.JSON(), nullable=True))

    # The unique constraint cannot be created while duplicates exist. Nothing
    # enforced uniqueness before this revision, so collapse any duplicate
    # (vendor_slug, digest) pairs to their earliest row first. Identical digest
    # means identical content, so this discards no information.
    op.execute(
        """
        DELETE FROM spec_snapshots
        WHERE id NOT IN (
            SELECT MIN(id) FROM spec_snapshots GROUP BY vendor_slug, digest
        )
        """
    )

    with op.batch_alter_table('spec_snapshots') as batch:
        batch.alter_column(
            'spec_format', existing_type=sa.String(length=8), nullable=False
        )
        batch.create_unique_constraint(
            'uq_spec_snapshots_vendor_digest', ['vendor_slug', 'digest']
        )


def downgrade() -> None:
    with op.batch_alter_table('spec_snapshots') as batch:
        batch.drop_constraint('uq_spec_snapshots_vendor_digest', type_='unique')
    op.drop_column('spec_snapshots', 'content')
    op.drop_column('spec_snapshots', 'spec_format')
    op.drop_table('spec_pointers')
