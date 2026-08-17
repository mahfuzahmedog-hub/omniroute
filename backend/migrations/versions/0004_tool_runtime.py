"""tool runtime

Revision ID: 0004_tool_runtime
Revises: 0003_agent_executions
Create Date: 2026-08-17 06:48:00.675340
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

import forge.db


revision: str = '0004_tool_runtime'
down_revision: str | None = '0003_agent_executions'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'project_tool_grants',
        sa.Column('project_id', forge.db.GUID(), nullable=False),
        sa.Column('permission', sa.String(length=32), nullable=False),
        sa.Column('auto_approve', sa.Boolean(), nullable=False),
        sa.Column('allowed_hosts', sa.JSON(), nullable=True),
        sa.Column('id', forge.db.GUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'permission', name='uq_project_tool_grant'),
    )
    with op.batch_alter_table('project_tool_grants', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_project_tool_grants_permission'), ['permission'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_project_tool_grants_project_id'), ['project_id'], unique=False
        )

    op.create_table(
        'tool_invocations',
        sa.Column('project_id', forge.db.GUID(), nullable=False),
        sa.Column('run_id', forge.db.GUID(), nullable=True),
        sa.Column('task_id', forge.db.GUID(), nullable=True),
        sa.Column('agent_key', sa.String(length=64), nullable=True),
        sa.Column('tool_name', sa.String(length=64), nullable=False),
        sa.Column('tool_version', sa.String(length=32), nullable=False),
        sa.Column('permission', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('side_effect', sa.String(length=16), nullable=False),
        sa.Column('cost_class', sa.String(length=16), nullable=False),
        sa.Column('args_metadata', sa.JSON(), nullable=True),
        sa.Column('result_summary', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('id', forge.db.GUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('tool_invocations', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_tool_invocations_agent_key'), ['agent_key'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_tool_invocations_permission'), ['permission'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_tool_invocations_project_id'), ['project_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_tool_invocations_run_id'), ['run_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_tool_invocations_status'), ['status'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_tool_invocations_task_id'), ['task_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_tool_invocations_tool_name'), ['tool_name'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('tool_invocations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tool_invocations_tool_name'))
        batch_op.drop_index(batch_op.f('ix_tool_invocations_task_id'))
        batch_op.drop_index(batch_op.f('ix_tool_invocations_status'))
        batch_op.drop_index(batch_op.f('ix_tool_invocations_run_id'))
        batch_op.drop_index(batch_op.f('ix_tool_invocations_project_id'))
        batch_op.drop_index(batch_op.f('ix_tool_invocations_permission'))
        batch_op.drop_index(batch_op.f('ix_tool_invocations_agent_key'))

    op.drop_table('tool_invocations')

    with op.batch_alter_table('project_tool_grants', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_project_tool_grants_project_id'))
        batch_op.drop_index(batch_op.f('ix_project_tool_grants_permission'))

    op.drop_table('project_tool_grants')
