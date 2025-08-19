"""create_core_database_schema

Revision ID: b6a2d6a86874
Revises:
Create Date: 2025-08-18 23:11:01.671588+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6a2d6a86874"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration changes."""
    # ENUM types will be created automatically by SQLAlchemy when tables are created

    # Create repositories table
    op.create_table(
        'repositories',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('url', sa.String(500), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('status', sa.Enum('active', 'suspended', 'error', name='repository_status'), nullable=False, server_default='active'),
        sa.Column('failure_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('config_override', sa.JSON(), nullable=True),
        sa.Column('last_polled_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url', name='uq_repositories_url')
    )

    # Create pull_requests table
    op.create_table(
        'pull_requests',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('repository_id', postgresql.UUID(), nullable=False),
        sa.Column('pr_number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('author', sa.String(100), nullable=False),
        sa.Column('state', sa.Enum('opened', 'closed', 'merged', name='pr_state'), nullable=False),
        sa.Column('draft', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('base_branch', sa.String(200), nullable=False),
        sa.Column('head_branch', sa.String(200), nullable=False),
        sa.Column('base_sha', sa.String(40), nullable=False),
        sa.Column('head_sha', sa.String(40), nullable=False),
        sa.Column('url', sa.String(500), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('last_checked_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('repository_id', 'pr_number', name='uq_pr_repo_number')
    )

    # Create check_runs table
    op.create_table(
        'check_runs',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('pr_id', postgresql.UUID(), nullable=False),
        sa.Column('external_id', sa.String(100), nullable=False),
        sa.Column('check_name', sa.String(200), nullable=False),
        sa.Column('check_suite_id', sa.String(100), nullable=True),
        sa.Column('status', sa.Enum('queued', 'in_progress', 'completed', 'cancelled', name='check_status'), nullable=False),
        sa.Column('conclusion', sa.Enum('success', 'failure', 'neutral', 'cancelled', 'timed_out', 'action_required', 'stale', 'skipped', name='check_conclusion'), nullable=True),
        sa.Column('logs_url', sa.String(500), nullable=True),
        sa.Column('details_url', sa.String(500), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['pr_id'], ['pull_requests.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_id', name='uq_check_runs_external_id')
    )

    # Create pr_state_history table (audit table)
    op.create_table(
        'pr_state_history',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('pr_id', postgresql.UUID(), nullable=False),
        sa.Column('old_state', sa.Enum('opened', 'closed', 'merged', name='pr_state'), nullable=True),
        sa.Column('new_state', sa.Enum('opened', 'closed', 'merged', name='pr_state'), nullable=False),
        sa.Column('trigger_event', sa.Enum('opened', 'synchronize', 'closed', 'reopened', 'edited', 'manual_check', name='trigger_event'), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['pr_id'], ['pull_requests.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create future-ready tables for Phase 2

    # Create analysis_results table
    op.create_table(
        'analysis_results',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('check_run_id', postgresql.UUID(), nullable=False),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=False),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('recommended_action', sa.String(100), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['check_run_id'], ['check_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create fix_attempts table
    op.create_table(
        'fix_attempts',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('analysis_result_id', postgresql.UUID(), nullable=False),
        sa.Column('fix_strategy', sa.String(100), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('success', sa.Boolean(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['analysis_result_id'], ['analysis_results.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create reviews table
    op.create_table(
        'reviews',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('pr_id', postgresql.UUID(), nullable=False),
        sa.Column('reviewer_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('decision', sa.String(50), nullable=True),
        sa.Column('feedback', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['pr_id'], ['pull_requests.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create performance indexes
    
    # Repositories indexes
    op.create_index('idx_repositories_status', 'repositories', ['status'])
    op.create_index('idx_repositories_last_polled', 'repositories', ['last_polled_at'])
    
    # Pull requests indexes
    op.create_index('idx_pull_requests_repository_id', 'pull_requests', ['repository_id'])
    op.create_index('idx_pull_requests_state', 'pull_requests', ['state'])
    op.create_index('idx_pull_requests_last_checked', 'pull_requests', ['last_checked_at'])
    op.create_index('idx_pull_requests_created_at', 'pull_requests', ['created_at'])
    op.create_index('idx_pull_requests_repo_state', 'pull_requests', ['repository_id', 'state'])
    
    # Check runs indexes
    op.create_index('idx_check_runs_pr_id', 'check_runs', ['pr_id'])
    op.create_index('idx_check_runs_status', 'check_runs', ['status'])
    op.create_index('idx_check_runs_conclusion', 'check_runs', ['conclusion'])
    op.create_index('idx_check_runs_check_name', 'check_runs', ['check_name'])
    op.create_index('idx_check_runs_created_at', 'check_runs', ['created_at'])
    op.create_index('idx_check_runs_pr_status', 'check_runs', ['pr_id', 'status'])
    op.create_index('idx_check_runs_pr_conclusion', 'check_runs', ['pr_id', 'conclusion'])
    
    # PR state history indexes
    op.create_index('idx_pr_state_history_pr_id', 'pr_state_history', ['pr_id'])
    op.create_index('idx_pr_state_history_created_at', 'pr_state_history', ['created_at'])
    op.create_index('idx_pr_state_history_trigger_event', 'pr_state_history', ['trigger_event'])
    op.create_index('idx_pr_state_history_pr_created', 'pr_state_history', ['pr_id', 'created_at'])
    
    # Analysis results indexes
    op.create_index('idx_analysis_results_check_run_id', 'analysis_results', ['check_run_id'])
    op.create_index('idx_analysis_results_category', 'analysis_results', ['category'])
    op.create_index('idx_analysis_results_confidence', 'analysis_results', ['confidence_score'])
    
    # Fix attempts indexes
    op.create_index('idx_fix_attempts_analysis_result_id', 'fix_attempts', ['analysis_result_id'])
    op.create_index('idx_fix_attempts_status', 'fix_attempts', ['status'])
    op.create_index('idx_fix_attempts_success', 'fix_attempts', ['success'])
    
    # Reviews indexes
    op.create_index('idx_reviews_pr_id', 'reviews', ['pr_id'])
    op.create_index('idx_reviews_reviewer_type', 'reviews', ['reviewer_type'])
    op.create_index('idx_reviews_status', 'reviews', ['status'])

    # Create database triggers for audit logging

    # Function to update updated_at timestamp
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)

    # Triggers for updated_at columns (with DROP IF EXISTS for idempotency)
    op.execute("DROP TRIGGER IF EXISTS update_repositories_updated_at ON repositories")
    op.execute("""
        CREATE TRIGGER update_repositories_updated_at
            BEFORE UPDATE ON repositories
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("DROP TRIGGER IF EXISTS update_pull_requests_updated_at ON pull_requests")
    op.execute("""
        CREATE TRIGGER update_pull_requests_updated_at
            BEFORE UPDATE ON pull_requests
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("DROP TRIGGER IF EXISTS update_check_runs_updated_at ON check_runs")
    op.execute("""
        CREATE TRIGGER update_check_runs_updated_at
            BEFORE UPDATE ON check_runs
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)

    # Function to log PR state changes
    op.execute("""
        CREATE OR REPLACE FUNCTION log_pr_state_change()
        RETURNS TRIGGER AS $$
        BEGIN
            IF (TG_OP = 'UPDATE' AND OLD.state != NEW.state) THEN
                INSERT INTO pr_state_history (
                    id, pr_id, old_state, new_state, trigger_event, metadata
                ) VALUES (
                    gen_random_uuid(),
                    NEW.id,
                    OLD.state,
                    NEW.state,
                    'manual_check'::trigger_event,
                    jsonb_build_object(
                        'old_head_sha', OLD.head_sha,
                        'new_head_sha', NEW.head_sha,
                        'updated_by', 'system'
                    )
                );
            ELSIF (TG_OP = 'INSERT') THEN
                INSERT INTO pr_state_history (
                    id, pr_id, old_state, new_state, trigger_event, metadata
                ) VALUES (
                    gen_random_uuid(),
                    NEW.id,
                    NULL,
                    NEW.state,
                    'opened'::trigger_event,
                    jsonb_build_object(
                        'head_sha', NEW.head_sha,
                        'created_by', 'system'
                    )
                );
            END IF;
            RETURN COALESCE(NEW, OLD);
        END;
        $$ language 'plpgsql';
    """)

    # Trigger for PR state changes
    op.execute("DROP TRIGGER IF EXISTS log_pull_request_state_changes ON pull_requests")
    op.execute("""
        CREATE TRIGGER log_pull_request_state_changes
            AFTER INSERT OR UPDATE ON pull_requests
            FOR EACH ROW
            EXECUTE FUNCTION log_pr_state_change();
    """)


def downgrade() -> None:
    """Revert migration changes."""
    # Drop triggers first
    op.execute("DROP TRIGGER IF EXISTS log_pull_request_state_changes ON pull_requests")
    op.execute("DROP TRIGGER IF EXISTS update_check_runs_updated_at ON check_runs")
    op.execute("DROP TRIGGER IF EXISTS update_pull_requests_updated_at ON pull_requests")
    op.execute("DROP TRIGGER IF EXISTS update_repositories_updated_at ON repositories")
    
    # Drop trigger functions
    op.execute("DROP FUNCTION IF EXISTS log_pr_state_change()")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    
    # Drop indexes
    op.drop_index('idx_reviews_status', table_name='reviews')
    op.drop_index('idx_reviews_reviewer_type', table_name='reviews')
    op.drop_index('idx_reviews_pr_id', table_name='reviews')
    
    op.drop_index('idx_fix_attempts_success', table_name='fix_attempts')
    op.drop_index('idx_fix_attempts_status', table_name='fix_attempts')
    op.drop_index('idx_fix_attempts_analysis_result_id', table_name='fix_attempts')
    
    op.drop_index('idx_analysis_results_confidence', table_name='analysis_results')
    op.drop_index('idx_analysis_results_category', table_name='analysis_results')
    op.drop_index('idx_analysis_results_check_run_id', table_name='analysis_results')
    
    op.drop_index('idx_pr_state_history_pr_created', table_name='pr_state_history')
    op.drop_index('idx_pr_state_history_trigger_event', table_name='pr_state_history')
    op.drop_index('idx_pr_state_history_created_at', table_name='pr_state_history')
    op.drop_index('idx_pr_state_history_pr_id', table_name='pr_state_history')
    
    op.drop_index('idx_check_runs_pr_conclusion', table_name='check_runs')
    op.drop_index('idx_check_runs_pr_status', table_name='check_runs')
    op.drop_index('idx_check_runs_created_at', table_name='check_runs')
    op.drop_index('idx_check_runs_check_name', table_name='check_runs')
    op.drop_index('idx_check_runs_conclusion', table_name='check_runs')
    op.drop_index('idx_check_runs_status', table_name='check_runs')
    op.drop_index('idx_check_runs_pr_id', table_name='check_runs')
    
    op.drop_index('idx_pull_requests_repo_state', table_name='pull_requests')
    op.drop_index('idx_pull_requests_created_at', table_name='pull_requests')
    op.drop_index('idx_pull_requests_last_checked', table_name='pull_requests')
    op.drop_index('idx_pull_requests_state', table_name='pull_requests')
    op.drop_index('idx_pull_requests_repository_id', table_name='pull_requests')
    
    op.drop_index('idx_repositories_last_polled', table_name='repositories')
    op.drop_index('idx_repositories_status', table_name='repositories')
    
    # Drop tables in reverse order (respecting foreign key dependencies)
    op.drop_table('reviews')
    op.drop_table('fix_attempts')
    op.drop_table('analysis_results')
    op.drop_table('pr_state_history')
    op.drop_table('check_runs')
    op.drop_table('pull_requests')
    op.drop_table('repositories')
    
    # Drop ENUM types
    op.execute("DROP TYPE IF EXISTS trigger_event")
    op.execute("DROP TYPE IF EXISTS repository_status")
    op.execute("DROP TYPE IF EXISTS check_conclusion")
    op.execute("DROP TYPE IF EXISTS check_status")
    op.execute("DROP TYPE IF EXISTS pr_state")
