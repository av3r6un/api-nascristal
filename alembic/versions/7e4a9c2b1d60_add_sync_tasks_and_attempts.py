"""Add MoySklad webhook queue and processing history."""
from alembic import op
import sqlalchemy as sa


revision = '7e4a9c2b1d60'
down_revision = '59ca8b5b7134'
branch_labels = None
depends_on = None


def upgrade():
  op.create_table(
    'sync_tasks',
    sa.Column('id', sa.Integer(), primary_key=True),
    sa.Column('entity_type', sa.String(32), nullable=False),
    sa.Column('entity_uuid', sa.Uuid(), nullable=False),
    sa.Column('action', sa.String(16), nullable=False),
    sa.Column('status', sa.String(16), nullable=False),
    sa.Column('request_id', sa.Uuid(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('created', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.UniqueConstraint('entity_type', 'entity_uuid', name='uq_sync_tasks_entity'),
    mysql_default_charset='utf8mb4', mysql_collate='utf8mb4_general_ci',
  )
  op.create_index('ix_sync_tasks_status_updated', 'sync_tasks', ['status', 'updated'])
  op.create_table(
    'sync_attempts',
    sa.Column('id', sa.Integer(), primary_key=True),
    sa.Column('task_id', sa.Integer(), sa.ForeignKey('sync_tasks.id'), nullable=False),
    sa.Column('status', sa.String(16), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    mysql_default_charset='utf8mb4', mysql_collate='utf8mb4_general_ci',
  )
  op.create_index('ix_sync_attempts_task_id', 'sync_attempts', ['task_id'])
  op.create_index('ix_sync_attempts_created', 'sync_attempts', ['created'])


def downgrade():
  op.drop_table('sync_attempts')
  op.drop_table('sync_tasks')
