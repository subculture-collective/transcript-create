"""Add security tables for API keys and audit logs

Revision ID: security_hardening_001
Revises: 94e8fe9e40fa
Create Date: 2025-10-26 04:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'security_hardening_001'
down_revision: Union[str, None] = '94e8fe9e40fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add API keys and audit logs tables."""
    
    # Create API keys table
    op.create_table(
        'api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('key_hash', sa.Text(), nullable=False),
        sa.Column('key_prefix', sa.Text(), nullable=False, comment='First 8 chars for display (e.g., "tc_abc12...")'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('scopes', sa.Text(), nullable=True, comment='Comma-separated API scopes (future use)'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash')
    )
    op.create_index('api_keys_user_id_idx', 'api_keys', ['user_id'])
    op.create_index('api_keys_key_hash_idx', 'api_keys', ['key_hash'])
    
    # Create audit logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.Text(), nullable=False, comment='Action type: login, logout, api_key_created, etc.'),
        sa.Column('resource_type', sa.Text(), nullable=True, comment='Type of resource affected'),
        sa.Column('resource_id', sa.Text(), nullable=True, comment='ID of resource affected'),
        sa.Column('ip_address', sa.Text(), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, default=True),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('audit_logs_user_id_idx', 'audit_logs', ['user_id'])
    op.create_index('audit_logs_action_idx', 'audit_logs', ['action'])
    op.create_index('audit_logs_created_at_idx', 'audit_logs', ['created_at'])
    
    # Add role column to users table if not exists
    # Note: Using op.execute to avoid errors if column already exists
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='users' AND column_name='role'
            ) THEN
                ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user';
                CREATE INDEX users_role_idx ON users(role);
            END IF;
        END $$;
    """)
    
    # Update sessions table to have proper expiration (if not set)
    op.execute("""
        UPDATE sessions 
        SET expires_at = created_at + interval '24 hours'
        WHERE expires_at IS NULL;
    """)


def downgrade() -> None:
    """Remove security tables."""
    op.drop_index('audit_logs_created_at_idx', table_name='audit_logs')
    op.drop_index('audit_logs_action_idx', table_name='audit_logs')
    op.drop_index('audit_logs_user_id_idx', table_name='audit_logs')
    op.drop_table('audit_logs')
    
    op.drop_index('api_keys_key_hash_idx', table_name='api_keys')
    op.drop_index('api_keys_user_id_idx', table_name='api_keys')
    op.drop_table('api_keys')
    
    # Note: We don't remove the role column from users to avoid data loss
    # Manually remove if needed: ALTER TABLE users DROP COLUMN role;
