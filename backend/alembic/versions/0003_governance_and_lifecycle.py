"""governance (reviews, concerns) and lifecycle (deployments, alerts) columns

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-10 14:30:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

_EMPTY_LIST = sa.text("'[]'::jsonb")


def upgrade() -> None:
    op.add_column('assessments', sa.Column('reassessment_of_deployment_id', sa.Integer(), nullable=True))
    op.create_foreign_key('assessments_reassessment_of_deployment_id_fkey', 'assessments', 'deployments',
                          ['reassessment_of_deployment_id'], ['id'])
    op.create_index('ix_assessments_reassessment_of_deployment_id', 'assessments', ['reassessment_of_deployment_id'])

    op.add_column('reviews', sa.Column('round', sa.Integer(), server_default=sa.text('1'), nullable=False))
    op.add_column('reviews', sa.Column('responsibilities', postgresql.JSONB(astext_type=sa.Text()), server_default=_EMPTY_LIST, nullable=False))
    op.add_column('reviews', sa.Column('selection_reason', sa.Text(), server_default='', nullable=False))

    op.add_column('concerns', sa.Column('area', sa.String(), nullable=True))
    op.add_column('concerns', sa.Column('assigned_to_id', sa.Integer(), nullable=True))
    op.create_foreign_key('concerns_assigned_to_id_fkey', 'concerns', 'users', ['assigned_to_id'], ['id'])
    op.create_index('ix_concerns_assigned_to_id', 'concerns', ['assigned_to_id'])

    op.add_column('deployments', sa.Column('status_reason', sa.Text(), server_default='', nullable=False))
    op.add_column('deployments', sa.Column('condition_status', postgresql.JSONB(astext_type=sa.Text()), server_default=_EMPTY_LIST, nullable=False))
    op.add_column('deployments', sa.Column('compliance_note', sa.Text(), server_default='', nullable=False))
    op.add_column('deployments', sa.Column('replaced_by_deployment_id', sa.Integer(), nullable=True))
    op.add_column('deployments', sa.Column('retired_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key('deployments_replaced_by_deployment_id_fkey', 'deployments', 'deployments',
                          ['replaced_by_deployment_id'], ['id'])
    op.create_index('ix_deployments_replaced_by_deployment_id', 'deployments', ['replaced_by_deployment_id'])

    op.add_column('alerts', sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('alerts', sa.Column('note', sa.Text(), server_default='', nullable=False))


def downgrade() -> None:
    op.drop_column('alerts', 'note')
    op.drop_column('alerts', 'acknowledged_at')
    op.drop_index('ix_deployments_replaced_by_deployment_id', table_name='deployments')
    op.drop_constraint('deployments_replaced_by_deployment_id_fkey', 'deployments', type_='foreignkey')
    op.drop_column('deployments', 'retired_at')
    op.drop_column('deployments', 'replaced_by_deployment_id')
    op.drop_column('deployments', 'compliance_note')
    op.drop_column('deployments', 'condition_status')
    op.drop_column('deployments', 'status_reason')
    op.drop_index('ix_concerns_assigned_to_id', table_name='concerns')
    op.drop_constraint('concerns_assigned_to_id_fkey', 'concerns', type_='foreignkey')
    op.drop_column('concerns', 'assigned_to_id')
    op.drop_column('concerns', 'area')
    op.drop_column('reviews', 'selection_reason')
    op.drop_column('reviews', 'responsibilities')
    op.drop_column('reviews', 'round')
    op.drop_index('ix_assessments_reassessment_of_deployment_id', table_name='assessments')
    op.drop_constraint('assessments_reassessment_of_deployment_id_fkey', 'assessments', type_='foreignkey')
    op.drop_column('assessments', 'reassessment_of_deployment_id')
