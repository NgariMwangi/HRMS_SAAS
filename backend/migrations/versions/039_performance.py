"""Company performance management and appraisal records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "039_performance"
down_revision = "038_hr_permissions"
branch_labels = None
depends_on = None

def _rls(table):
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    scope = "current_setting('app.is_platform_admin', true) = 'true' OR tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid"
    op.execute(f"CREATE POLICY tenant_isolation_{table} ON {table} USING ({scope}) WITH CHECK ({scope})")

def upgrade():
    # New tables only; existing HRMS data is untouched.
    op.create_table('performance_competencies',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('definition', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_performance_competencies_company_id'), 'performance_competencies', ['company_id'], unique=False)
    op.create_index(op.f('ix_performance_competencies_tenant_id'), 'performance_competencies', ['tenant_id'], unique=False)
    op.create_table('performance_cycles',
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('frequency', sa.String(length=30), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('windows', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('start_date < end_date', name='ck_performance_cycle_dates'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_performance_cycles_company_id'), 'performance_cycles', ['company_id'], unique=False)
    op.create_index(op.f('ix_performance_cycles_tenant_id'), 'performance_cycles', ['tenant_id'], unique=False)
    op.create_table('performance_rating_scales',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('levels', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_performance_rating_scales_company_id'), 'performance_rating_scales', ['company_id'], unique=False)
    op.create_index(op.f('ix_performance_rating_scales_tenant_id'), 'performance_rating_scales', ['tenant_id'], unique=False)
    op.create_table('performance_settings',
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('company_id')
    )
    op.create_index(op.f('ix_performance_settings_company_id'), 'performance_settings', ['company_id'], unique=False)
    op.create_index(op.f('ix_performance_settings_tenant_id'), 'performance_settings', ['tenant_id'], unique=False)
    op.create_table('performance_participants',
    sa.Column('cycle_id', sa.UUID(), nullable=False),
    sa.Column('employee_id', sa.UUID(), nullable=False),
    sa.Column('manager_id', sa.UUID(), nullable=True),
    sa.Column('reviewer_id', sa.UUID(), nullable=True),
    sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['cycle_id'], ['performance_cycles.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['manager_id'], ['employees.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reviewer_id'], ['employees.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cycle_id', 'employee_id', name='uq_performance_participant')
    )
    op.create_index(op.f('ix_performance_participants_company_id'), 'performance_participants', ['company_id'], unique=False)
    op.create_index(op.f('ix_performance_participants_cycle_id'), 'performance_participants', ['cycle_id'], unique=False)
    op.create_index(op.f('ix_performance_participants_employee_id'), 'performance_participants', ['employee_id'], unique=False)
    op.create_index(op.f('ix_performance_participants_manager_id'), 'performance_participants', ['manager_id'], unique=False)
    op.create_index(op.f('ix_performance_participants_tenant_id'), 'performance_participants', ['tenant_id'], unique=False)
    op.create_table('performance_appraisals',
    sa.Column('participant_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('self_assessment', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('manager_assessment', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('competencies', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('review', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('acknowledgement', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('scores', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('finalized_at', sa.DateTime(), nullable=True),
    sa.Column('finalized_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['finalized_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['participant_id'], ['performance_participants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('participant_id')
    )
    op.create_index(op.f('ix_performance_appraisals_company_id'), 'performance_appraisals', ['company_id'], unique=False)
    op.create_index(op.f('ix_performance_appraisals_participant_id'), 'performance_appraisals', ['participant_id'], unique=False)
    op.create_index(op.f('ix_performance_appraisals_tenant_id'), 'performance_appraisals', ['tenant_id'], unique=False)
    op.create_table('performance_check_ins',
    sa.Column('appraisal_id', sa.UUID(), nullable=False),
    sa.Column('recorded_by', sa.UUID(), nullable=False),
    sa.Column('meeting_date', sa.Date(), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['appraisal_id'], ['performance_appraisals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recorded_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_performance_check_ins_appraisal_id'), 'performance_check_ins', ['appraisal_id'], unique=False)
    op.create_index(op.f('ix_performance_check_ins_company_id'), 'performance_check_ins', ['company_id'], unique=False)
    op.create_index(op.f('ix_performance_check_ins_tenant_id'), 'performance_check_ins', ['tenant_id'], unique=False)
    op.create_table('performance_development_actions',
    sa.Column('appraisal_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('progress', sa.Numeric(precision=7, scale=2), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('progress >= 0 AND progress <= 100', name='ck_development_progress'),
    sa.ForeignKeyConstraint(['appraisal_id'], ['performance_appraisals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['employees.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_performance_development_actions_appraisal_id'), 'performance_development_actions', ['appraisal_id'], unique=False)
    op.create_index(op.f('ix_performance_development_actions_company_id'), 'performance_development_actions', ['company_id'], unique=False)
    op.create_index(op.f('ix_performance_development_actions_tenant_id'), 'performance_development_actions', ['tenant_id'], unique=False)
    op.create_table('performance_events',
    sa.Column('appraisal_id', sa.UUID(), nullable=True),
    sa.Column('actor_id', sa.UUID(), nullable=False),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['appraisal_id'], ['performance_appraisals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_performance_events_appraisal_id'), 'performance_events', ['appraisal_id'], unique=False)
    op.create_index(op.f('ix_performance_events_company_id'), 'performance_events', ['company_id'], unique=False)
    op.create_index(op.f('ix_performance_events_entity_id'), 'performance_events', ['entity_id'], unique=False)
    op.create_index(op.f('ix_performance_events_tenant_id'), 'performance_events', ['tenant_id'], unique=False)
    op.create_table('performance_goals',
    sa.Column('appraisal_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('definition', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('weight', sa.Numeric(precision=7, scale=2), nullable=False),
    sa.Column('progress', sa.Numeric(precision=7, scale=2), nullable=False),
    sa.Column('actual', sa.Numeric(precision=20, scale=4), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('approval', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('progress >= 0 AND progress <= 100', name='ck_performance_goal_progress'),
    sa.CheckConstraint('weight >= 0 AND weight <= 100', name='ck_performance_goal_weight'),
    sa.ForeignKeyConstraint(['appraisal_id'], ['performance_appraisals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_performance_goals_appraisal_id'), 'performance_goals', ['appraisal_id'], unique=False)
    op.create_index(op.f('ix_performance_goals_company_id'), 'performance_goals', ['company_id'], unique=False)
    op.create_index(op.f('ix_performance_goals_tenant_id'), 'performance_goals', ['tenant_id'], unique=False)
    op.create_table('performance_notifications',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('event_key', sa.String(length=180), nullable=False),
    sa.Column('message', sa.String(length=500), nullable=False),
    sa.Column('appraisal_id', sa.UUID(), nullable=True),
    sa.Column('read_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['appraisal_id'], ['performance_appraisals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'event_key', name='uq_performance_notice')
    )
    op.create_index(op.f('ix_performance_notifications_company_id'), 'performance_notifications', ['company_id'], unique=False)
    op.create_index(op.f('ix_performance_notifications_tenant_id'), 'performance_notifications', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_performance_notifications_user_id'), 'performance_notifications', ['user_id'], unique=False)
    op.create_table('performance_pips',
    sa.Column('employee_id', sa.UUID(), nullable=False),
    sa.Column('manager_id', sa.UUID(), nullable=False),
    sa.Column('hr_owner_id', sa.UUID(), nullable=False),
    sa.Column('appraisal_id', sa.UUID(), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('start_date < end_date', name='ck_performance_pip_dates'),
    sa.ForeignKeyConstraint(['appraisal_id'], ['performance_appraisals.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['hr_owner_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['manager_id'], ['employees.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_performance_pips_company_id'), 'performance_pips', ['company_id'], unique=False)
    op.create_index(op.f('ix_performance_pips_employee_id'), 'performance_pips', ['employee_id'], unique=False)
    op.create_index(op.f('ix_performance_pips_tenant_id'), 'performance_pips', ['tenant_id'], unique=False)
    op.create_table('performance_goal_evidence',
    sa.Column('goal_id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['document_id'], ['employee_documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['goal_id'], ['performance_goals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('document_id')
    )
    op.create_index(op.f('ix_performance_goal_evidence_company_id'), 'performance_goal_evidence', ['company_id'], unique=False)
    op.create_index(op.f('ix_performance_goal_evidence_goal_id'), 'performance_goal_evidence', ['goal_id'], unique=False)
    op.create_index(op.f('ix_performance_goal_evidence_tenant_id'), 'performance_goal_evidence', ['tenant_id'], unique=False)
    op.create_table('performance_goal_progress',
    sa.Column('goal_id', sa.UUID(), nullable=False),
    sa.Column('recorded_by', sa.UUID(), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['goal_id'], ['performance_goals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recorded_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_performance_goal_progress_company_id'), 'performance_goal_progress', ['company_id'], unique=False)
    op.create_index(op.f('ix_performance_goal_progress_goal_id'), 'performance_goal_progress', ['goal_id'], unique=False)
    op.create_index(op.f('ix_performance_goal_progress_tenant_id'), 'performance_goal_progress', ['tenant_id'], unique=False)
    op.create_table('performance_pip_reviews',
    sa.Column('pip_id', sa.UUID(), nullable=False),
    sa.Column('recorded_by', sa.UUID(), nullable=False),
    sa.Column('meeting_date', sa.Date(), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['pip_id'], ['performance_pips.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recorded_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_performance_pip_reviews_company_id'), 'performance_pip_reviews', ['company_id'], unique=False)
    op.create_index(op.f('ix_performance_pip_reviews_pip_id'), 'performance_pip_reviews', ['pip_id'], unique=False)
    op.create_index(op.f('ix_performance_pip_reviews_tenant_id'), 'performance_pip_reviews', ['tenant_id'], unique=False)

    op.create_check_constraint('ck_performance_cycle_status', 'performance_cycles', "status IN ('DRAFT','GOAL_SETTING','ACTIVE','SELF_ASSESSMENT','MANAGER_ASSESSMENT','REVIEW','CALIBRATION','FINALIZATION','COMPLETED')")
    op.create_check_constraint('ck_performance_cycle_version', 'performance_cycles', 'version >= 1')
    op.create_check_constraint('ck_performance_not_self_appraiser', 'performance_participants', 'employee_id <> manager_id AND employee_id <> reviewer_id')
    op.create_check_constraint('ck_performance_appraisal_status', 'performance_appraisals', "status IN ('GOAL_SETTING','ACTIVE','SELF_ASSESSMENT','MANAGER_ASSESSMENT','REVIEW','CALIBRATION','FINALIZATION','FINALIZED')")
    op.create_check_constraint('ck_performance_appraisal_version', 'performance_appraisals', 'version >= 1')
    op.create_check_constraint('ck_development_status', 'performance_development_actions', "status IN ('NOT_STARTED','IN_PROGRESS','COMPLETED','CANCELLED')")
    op.create_check_constraint('ck_development_version', 'performance_development_actions', 'version >= 1')
    op.create_check_constraint('ck_performance_goal_status', 'performance_goals', "status IN ('DRAFT','PENDING_APPROVAL','APPROVED','IN_PROGRESS','COMPLETED','CANCELLED')")
    op.create_check_constraint('ck_performance_goal_version', 'performance_goals', 'version >= 1')
    op.create_check_constraint('ck_performance_pip_manager', 'performance_pips', 'employee_id <> manager_id')
    op.create_check_constraint('ck_performance_pip_status', 'performance_pips', "status IN ('DRAFT','ACTIVE','EXTENDED','SUCCESSFUL','UNSUCCESSFUL','CANCELLED')")
    op.create_check_constraint('ck_performance_pip_version', 'performance_pips', 'version >= 1')
    _rls("performance_competencies")
    _rls("performance_cycles")
    _rls("performance_rating_scales")
    _rls("performance_settings")
    _rls("performance_participants")
    _rls("performance_appraisals")
    _rls("performance_check_ins")
    _rls("performance_development_actions")
    _rls("performance_events")
    _rls("performance_goals")
    _rls("performance_notifications")
    _rls("performance_pips")
    _rls("performance_goal_evidence")
    _rls("performance_goal_progress")
    _rls("performance_pip_reviews")

def downgrade():
    # New tables only; existing HRMS data is untouched.
    op.drop_index(op.f('ix_performance_pip_reviews_tenant_id'), table_name='performance_pip_reviews')
    op.drop_index(op.f('ix_performance_pip_reviews_pip_id'), table_name='performance_pip_reviews')
    op.drop_index(op.f('ix_performance_pip_reviews_company_id'), table_name='performance_pip_reviews')
    op.drop_table('performance_pip_reviews')
    op.drop_index(op.f('ix_performance_goal_progress_tenant_id'), table_name='performance_goal_progress')
    op.drop_index(op.f('ix_performance_goal_progress_goal_id'), table_name='performance_goal_progress')
    op.drop_index(op.f('ix_performance_goal_progress_company_id'), table_name='performance_goal_progress')
    op.drop_table('performance_goal_progress')
    op.drop_index(op.f('ix_performance_goal_evidence_tenant_id'), table_name='performance_goal_evidence')
    op.drop_index(op.f('ix_performance_goal_evidence_goal_id'), table_name='performance_goal_evidence')
    op.drop_index(op.f('ix_performance_goal_evidence_company_id'), table_name='performance_goal_evidence')
    op.drop_table('performance_goal_evidence')
    op.drop_index(op.f('ix_performance_pips_tenant_id'), table_name='performance_pips')
    op.drop_index(op.f('ix_performance_pips_employee_id'), table_name='performance_pips')
    op.drop_index(op.f('ix_performance_pips_company_id'), table_name='performance_pips')
    op.drop_table('performance_pips')
    op.drop_index(op.f('ix_performance_notifications_user_id'), table_name='performance_notifications')
    op.drop_index(op.f('ix_performance_notifications_tenant_id'), table_name='performance_notifications')
    op.drop_index(op.f('ix_performance_notifications_company_id'), table_name='performance_notifications')
    op.drop_table('performance_notifications')
    op.drop_index(op.f('ix_performance_goals_tenant_id'), table_name='performance_goals')
    op.drop_index(op.f('ix_performance_goals_company_id'), table_name='performance_goals')
    op.drop_index(op.f('ix_performance_goals_appraisal_id'), table_name='performance_goals')
    op.drop_table('performance_goals')
    op.drop_index(op.f('ix_performance_events_tenant_id'), table_name='performance_events')
    op.drop_index(op.f('ix_performance_events_entity_id'), table_name='performance_events')
    op.drop_index(op.f('ix_performance_events_company_id'), table_name='performance_events')
    op.drop_index(op.f('ix_performance_events_appraisal_id'), table_name='performance_events')
    op.drop_table('performance_events')
    op.drop_index(op.f('ix_performance_development_actions_tenant_id'), table_name='performance_development_actions')
    op.drop_index(op.f('ix_performance_development_actions_company_id'), table_name='performance_development_actions')
    op.drop_index(op.f('ix_performance_development_actions_appraisal_id'), table_name='performance_development_actions')
    op.drop_table('performance_development_actions')
    op.drop_index(op.f('ix_performance_check_ins_tenant_id'), table_name='performance_check_ins')
    op.drop_index(op.f('ix_performance_check_ins_company_id'), table_name='performance_check_ins')
    op.drop_index(op.f('ix_performance_check_ins_appraisal_id'), table_name='performance_check_ins')
    op.drop_table('performance_check_ins')
    op.drop_index(op.f('ix_performance_appraisals_tenant_id'), table_name='performance_appraisals')
    op.drop_index(op.f('ix_performance_appraisals_participant_id'), table_name='performance_appraisals')
    op.drop_index(op.f('ix_performance_appraisals_company_id'), table_name='performance_appraisals')
    op.drop_table('performance_appraisals')
    op.drop_index(op.f('ix_performance_participants_tenant_id'), table_name='performance_participants')
    op.drop_index(op.f('ix_performance_participants_manager_id'), table_name='performance_participants')
    op.drop_index(op.f('ix_performance_participants_employee_id'), table_name='performance_participants')
    op.drop_index(op.f('ix_performance_participants_cycle_id'), table_name='performance_participants')
    op.drop_index(op.f('ix_performance_participants_company_id'), table_name='performance_participants')
    op.drop_table('performance_participants')
    op.drop_index(op.f('ix_performance_settings_tenant_id'), table_name='performance_settings')
    op.drop_index(op.f('ix_performance_settings_company_id'), table_name='performance_settings')
    op.drop_table('performance_settings')
    op.drop_index(op.f('ix_performance_rating_scales_tenant_id'), table_name='performance_rating_scales')
    op.drop_index(op.f('ix_performance_rating_scales_company_id'), table_name='performance_rating_scales')
    op.drop_table('performance_rating_scales')
    op.drop_index(op.f('ix_performance_cycles_tenant_id'), table_name='performance_cycles')
    op.drop_index(op.f('ix_performance_cycles_company_id'), table_name='performance_cycles')
    op.drop_table('performance_cycles')
    op.drop_index(op.f('ix_performance_competencies_tenant_id'), table_name='performance_competencies')
    op.drop_index(op.f('ix_performance_competencies_company_id'), table_name='performance_competencies')
    op.drop_table('performance_competencies')


