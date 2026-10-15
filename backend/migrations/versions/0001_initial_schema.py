"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-15 22:01:42.987006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table('alerts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('kind', sa.String(length=48), nullable=False),
    sa.Column('severity', sa.String(length=16), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('ref_type', sa.String(length=32), nullable=True),
    sa.Column('ref_id', sa.String(length=64), nullable=True),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('acknowledged_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_alerts'))
    )
    op.create_index(op.f('ix_alerts_created_at'), 'alerts', ['created_at'], unique=False)
    op.create_table('audit_logs',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actor_type', sa.String(length=16), nullable=False),
    sa.Column('actor_id', sa.String(length=64), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('entity', sa.String(length=32), nullable=False),
    sa.Column('entity_id', sa.String(length=64), nullable=True),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    op.create_index('ix_audit_entity', 'audit_logs', ['entity', 'entity_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_table('customers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('whatsapp_opt_in', sa.Boolean(), nullable=False),
    sa.Column('whatsapp_opt_in_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('whatsapp_opt_in_source', sa.String(length=32), nullable=False),
    sa.Column('whatsapp_unavailable', sa.Boolean(), nullable=False),
    sa.Column('last_inbound_whatsapp_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('anonymized_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_customers')),
    sa.UniqueConstraint('phone', name=op.f('uq_customers_phone'))
    )
    op.create_table('dining_tables',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('area', sa.String(length=40), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('min_capacity', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('sort', sa.Integer(), nullable=False),
    sa.CheckConstraint('capacity >= 1 AND min_capacity >= 1 AND min_capacity <= capacity', name=op.f('ck_dining_tables_capacity')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_dining_tables')),
    sa.UniqueConstraint('code', name=op.f('uq_dining_tables_code'))
    )
    op.create_table('integration_status',
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_failure_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('consecutive_failures', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('name', name=op.f('pk_integration_status'))
    )
    op.create_table('jobs',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('kind', sa.String(length=64), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('run_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('dedupe_key', sa.String(length=160), nullable=True),
    sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_jobs')),
    sa.UniqueConstraint('dedupe_key', name=op.f('uq_jobs_dedupe_key'))
    )
    op.create_index('ix_jobs_ready', 'jobs', ['status', 'run_at'], unique=False)
    op.create_table('menu_categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('name_hi', sa.String(length=80), nullable=False),
    sa.Column('sort', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_menu_categories'))
    )
    op.create_table('restaurant_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('name_pronunciation', sa.String(length=200), nullable=False),
    sa.Column('legal_name', sa.String(length=200), nullable=False),
    sa.Column('address', sa.Text(), nullable=False),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('state', sa.String(length=100), nullable=False),
    sa.Column('state_code', sa.String(length=4), nullable=False),
    sa.Column('pincode', sa.String(length=10), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('maps_url', sa.String(length=500), nullable=False),
    sa.Column('gstin', sa.String(length=15), nullable=False),
    sa.Column('fssai_license', sa.String(length=20), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('arrival_instructions', sa.Text(), nullable=False),
    sa.Column('pickup_instructions', sa.Text(), nullable=False),
    sa.Column('languages', sa.JSON(), nullable=False),
    sa.Column('primary_language', sa.String(length=8), nullable=False),
    sa.Column('greeting_en', sa.Text(), nullable=False),
    sa.Column('greeting_hi', sa.Text(), nullable=False),
    sa.Column('ai_knowledge', sa.Text(), nullable=False),
    sa.Column('ai_enabled', sa.Boolean(), nullable=False),
    sa.Column('transfer_number', sa.String(length=20), nullable=False),
    sa.Column('staff_alert_numbers', sa.JSON(), nullable=False),
    sa.Column('opening_hours', sa.JSON(), nullable=False),
    sa.Column('reservations_enabled', sa.Boolean(), nullable=False),
    sa.Column('slot_interval_minutes', sa.Integer(), nullable=False),
    sa.Column('default_duration_minutes', sa.Integer(), nullable=False),
    sa.Column('duration_rules', sa.JSON(), nullable=False),
    sa.Column('buffer_minutes', sa.Integer(), nullable=False),
    sa.Column('min_notice_minutes', sa.Integer(), nullable=False),
    sa.Column('max_advance_days', sa.Integer(), nullable=False),
    sa.Column('min_party', sa.Integer(), nullable=False),
    sa.Column('max_party', sa.Integer(), nullable=False),
    sa.Column('hold_minutes', sa.Integer(), nullable=False),
    sa.Column('deposit_per_guest_paise', sa.Integer(), nullable=False),
    sa.Column('deposit_min_party', sa.Integer(), nullable=False),
    sa.Column('cancellation_cutoff_minutes', sa.Integer(), nullable=False),
    sa.Column('cancellation_policy', sa.Text(), nullable=False),
    sa.Column('no_show_grace_minutes', sa.Integer(), nullable=False),
    sa.Column('reminder_offsets_minutes', sa.JSON(), nullable=False),
    sa.Column('reminder_channels', sa.JSON(), nullable=False),
    sa.Column('ordering_enabled', sa.Boolean(), nullable=False),
    sa.Column('prep_target_minutes', sa.Integer(), nullable=False),
    sa.Column('kitchen_parallel_orders', sa.Integer(), nullable=False),
    sa.Column('max_active_orders', sa.Integer(), nullable=False),
    sa.Column('auto_accept_orders', sa.Boolean(), nullable=False),
    sa.Column('min_payment_type', sa.String(length=8), nullable=False),
    sa.Column('min_payment_value', sa.Integer(), nullable=False),
    sa.Column('default_tax_rate_bp', sa.Integer(), nullable=False),
    sa.Column('prices_include_tax', sa.Boolean(), nullable=False),
    sa.Column('charges', sa.JSON(), nullable=False),
    sa.Column('discounts', sa.JSON(), nullable=False),
    sa.Column('invoice_prefix', sa.String(length=16), nullable=False),
    sa.Column('next_invoice_number', sa.Integer(), nullable=False),
    sa.Column('whatsapp_templates', sa.JSON(), nullable=False),
    sa.Column('transcript_retention_days', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_restaurant_settings'))
    )
    op.create_table('special_days',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('closed', sa.Boolean(), nullable=False),
    sa.Column('intervals', sa.JSON(), nullable=False),
    sa.Column('note', sa.String(length=200), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_special_days')),
    sa.UniqueConstraint('day', name=op.f('uq_special_days_day'))
    )
    op.create_table('staff_users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('password_hash', sa.String(length=256), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_staff_users')),
    sa.UniqueConstraint('email', name=op.f('uq_staff_users_email'))
    )
    op.create_table('table_combinations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('min_capacity', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_table_combinations'))
    )
    op.create_table('usage_events',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('kind', sa.String(length=48), nullable=False),
    sa.Column('quantity', sa.BigInteger(), nullable=False),
    sa.Column('cost_paise', sa.BigInteger(), nullable=False),
    sa.Column('meta', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_usage_events'))
    )
    op.create_index(op.f('ix_usage_events_created_at'), 'usage_events', ['created_at'], unique=False)
    op.create_index(op.f('ix_usage_events_kind'), 'usage_events', ['kind'], unique=False)
    op.create_table('webhook_events',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('event_id', sa.String(length=128), nullable=False),
    sa.Column('event_type', sa.String(length=64), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_webhook_events')),
    sa.UniqueConstraint('provider', 'event_id', name='uq_webhook_provider_event')
    )
    op.create_index(op.f('ix_webhook_events_received_at'), 'webhook_events', ['received_at'], unique=False)
    op.create_table('worker_heartbeats',
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('beat_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('name', name=op.f('pk_worker_heartbeats'))
    )
    op.create_table('callback_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('reason', sa.String(length=300), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('handled_by', sa.Integer(), nullable=True),
    sa.Column('handled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('note', sa.String(length=300), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_callback_requests_customer_id_customers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_callback_requests'))
    )
    op.create_table('combination_tables',
    sa.Column('combination_id', sa.Integer(), nullable=False),
    sa.Column('table_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['combination_id'], ['table_combinations.id'], name=op.f('fk_combination_tables_combination_id_table_combinations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['table_id'], ['dining_tables.id'], name=op.f('fk_combination_tables_table_id_dining_tables'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('combination_id', 'table_id', name=op.f('pk_combination_tables'))
    )
    op.create_table('conversations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('external_id', sa.String(length=80), nullable=False),
    sa.Column('mode', sa.String(length=8), nullable=False),
    sa.Column('status', sa.String(length=8), nullable=False),
    sa.Column('handoff_reason', sa.String(length=200), nullable=False),
    sa.Column('handoff_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('assigned_to', sa.Integer(), nullable=True),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('transcript', sa.JSON(), nullable=False),
    sa.Column('state', sa.JSON(), nullable=False),
    sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('unread', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_conversations_customer_id_customers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations'))
    )
    op.create_index(op.f('ix_conversations_customer_id'), 'conversations', ['customer_id'], unique=False)
    op.create_index(op.f('ix_conversations_external_id'), 'conversations', ['external_id'], unique=False)
    op.create_index(op.f('ix_conversations_last_message_at'), 'conversations', ['last_message_at'], unique=False)
    op.create_table('menu_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('name_hi', sa.String(length=120), nullable=False),
    sa.Column('aliases', sa.JSON(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('price_paise', sa.Integer(), nullable=False),
    sa.Column('image_url', sa.String(length=500), nullable=False),
    sa.Column('dietary', sa.JSON(), nullable=False),
    sa.Column('allergens', sa.String(length=300), nullable=False),
    sa.Column('spice_level', sa.String(length=20), nullable=False),
    sa.Column('available', sa.Boolean(), nullable=False),
    sa.Column('prep_minutes', sa.Integer(), nullable=False),
    sa.Column('tax_rate_bp', sa.Integer(), nullable=True),
    sa.Column('sort', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['menu_categories.id'], name=op.f('fk_menu_items_category_id_menu_categories')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_menu_items'))
    )
    op.create_index(op.f('ix_menu_items_category_id'), 'menu_items', ['category_id'], unique=False)
    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('dedupe_key', sa.String(length=160), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('method', sa.String(length=16), nullable=False),
    sa.Column('wa_message_id', sa.String(length=128), nullable=True),
    sa.Column('error', sa.String(length=300), nullable=False),
    sa.Column('ref_type', sa.String(length=16), nullable=False),
    sa.Column('ref_id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_notifications_customer_id_customers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications')),
    sa.UniqueConstraint('dedupe_key', name=op.f('uq_notifications_dedupe_key'))
    )
    op.create_index(op.f('ix_notifications_created_at'), 'notifications', ['created_at'], unique=False)
    op.create_index(op.f('ix_notifications_customer_id'), 'notifications', ['customer_id'], unique=False)
    op.create_table('reservations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ref', sa.String(length=12), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('party_size', sa.Integer(), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('hold_reason', sa.String(length=16), nullable=True),
    sa.Column('hold_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('staff_notes', sa.Text(), nullable=False),
    sa.Column('deposit_paise', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('arrived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('seated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancel_reason', sa.String(length=200), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_reservations_customer_id_customers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reservations')),
    sa.UniqueConstraint('ref', name=op.f('uq_reservations_ref'))
    )
    op.create_index(op.f('ix_reservations_customer_id'), 'reservations', ['customer_id'], unique=False)
    op.create_index(op.f('ix_reservations_starts_at'), 'reservations', ['starts_at'], unique=False)
    op.create_index(op.f('ix_reservations_status'), 'reservations', ['status'], unique=False)
    op.create_table('staff_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['staff_users.id'], name=op.f('fk_staff_sessions_user_id_staff_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_staff_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_staff_sessions_token_hash'))
    )
    op.create_index(op.f('ix_staff_sessions_user_id'), 'staff_sessions', ['user_id'], unique=False)
    op.create_table('table_blocks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('table_id', sa.Integer(), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reason', sa.String(length=200), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['table_id'], ['dining_tables.id'], name=op.f('fk_table_blocks_table_id_dining_tables'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_table_blocks'))
    )
    op.create_index(op.f('ix_table_blocks_table_id'), 'table_blocks', ['table_id'], unique=False)
    op.create_table('calls',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('provider_call_id', sa.String(length=80), nullable=False),
    sa.Column('conversation_id', sa.Integer(), nullable=True),
    sa.Column('from_number', sa.String(length=20), nullable=False),
    sa.Column('to_number', sa.String(length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_seconds', sa.Integer(), nullable=False),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('turns', sa.Integer(), nullable=False),
    sa.Column('outcome', sa.String(length=16), nullable=False),
    sa.Column('error', sa.String(length=300), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_calls_conversation_id_conversations'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_calls')),
    sa.UniqueConstraint('provider_call_id', name=op.f('uq_calls_provider_call_id'))
    )
    op.create_index(op.f('ix_calls_started_at'), 'calls', ['started_at'], unique=False)
    op.create_table('menu_addon_groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('min_select', sa.Integer(), nullable=False),
    sa.Column('max_select', sa.Integer(), nullable=False),
    sa.Column('sort', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['menu_items.id'], name=op.f('fk_menu_addon_groups_item_id_menu_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_menu_addon_groups'))
    )
    op.create_index(op.f('ix_menu_addon_groups_item_id'), 'menu_addon_groups', ['item_id'], unique=False)
    op.create_table('menu_variants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('price_paise', sa.Integer(), nullable=False),
    sa.Column('available', sa.Boolean(), nullable=False),
    sa.Column('sort', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['menu_items.id'], name=op.f('fk_menu_variants_item_id_menu_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_menu_variants'))
    )
    op.create_index(op.f('ix_menu_variants_item_id'), 'menu_variants', ['item_id'], unique=False)
    op.create_table('messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('conversation_id', sa.Integer(), nullable=True),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('direction', sa.String(length=4), nullable=False),
    sa.Column('sender', sa.String(length=12), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('media', sa.String(length=16), nullable=False),
    sa.Column('template', sa.String(length=100), nullable=False),
    sa.Column('wa_message_id', sa.String(length=128), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('error', sa.String(length=300), nullable=False),
    sa.Column('staff_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_messages_conversation_id_conversations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_messages_customer_id_customers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages')),
    sa.UniqueConstraint('wa_message_id', name=op.f('uq_messages_wa_message_id'))
    )
    op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_messages_created_at'), 'messages', ['created_at'], unique=False)
    op.create_index(op.f('ix_messages_customer_id'), 'messages', ['customer_id'], unique=False)
    op.create_table('orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ref', sa.String(length=12), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('order_type', sa.String(length=16), nullable=False),
    sa.Column('reservation_id', sa.Integer(), nullable=True),
    sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('special_instructions', sa.Text(), nullable=False),
    sa.Column('bill', sa.JSON(), nullable=False),
    sa.Column('subtotal_paise', sa.Integer(), nullable=False),
    sa.Column('discount_paise', sa.Integer(), nullable=False),
    sa.Column('charges_paise', sa.Integer(), nullable=False),
    sa.Column('tax_paise', sa.Integer(), nullable=False),
    sa.Column('total_paise', sa.Integer(), nullable=False),
    sa.Column('amount_due_paise', sa.Integer(), nullable=False),
    sa.Column('amount_paid_paise', sa.Integer(), nullable=False),
    sa.Column('estimate_minutes', sa.Integer(), nullable=True),
    sa.Column('estimated_ready_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('invoice_number', sa.String(length=32), nullable=True),
    sa.Column('customer_gstin', sa.String(length=15), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ready_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancel_reason', sa.String(length=200), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_orders_customer_id_customers')),
    sa.ForeignKeyConstraint(['reservation_id'], ['reservations.id'], name=op.f('fk_orders_reservation_id_reservations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_orders')),
    sa.UniqueConstraint('invoice_number', name=op.f('uq_orders_invoice_number')),
    sa.UniqueConstraint('ref', name=op.f('uq_orders_ref'))
    )
    op.create_index(op.f('ix_orders_created_at'), 'orders', ['created_at'], unique=False)
    op.create_index(op.f('ix_orders_customer_id'), 'orders', ['customer_id'], unique=False)
    op.create_index(op.f('ix_orders_status'), 'orders', ['status'], unique=False)
    op.create_table('table_allocations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('table_id', sa.Integer(), nullable=False),
    sa.Column('reservation_id', sa.Integer(), nullable=True),
    sa.Column('block_id', sa.Integer(), nullable=True),
    sa.Column('period', postgresql.TSTZRANGE(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    postgresql.ExcludeConstraint((sa.column('table_id'), '='), (sa.column('period'), '&&'), where=sa.text('active'), using='gist', name='no_overlapping_allocations'),
    sa.CheckConstraint('(reservation_id IS NULL) <> (block_id IS NULL)', name=op.f('ck_table_allocations_one_owner')),
    sa.ForeignKeyConstraint(['block_id'], ['table_blocks.id'], name=op.f('fk_table_allocations_block_id_table_blocks'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reservation_id'], ['reservations.id'], name=op.f('fk_table_allocations_reservation_id_reservations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['table_id'], ['dining_tables.id'], name=op.f('fk_table_allocations_table_id_dining_tables'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_table_allocations'))
    )
    op.create_index(op.f('ix_table_allocations_block_id'), 'table_allocations', ['block_id'], unique=False)
    op.create_index(op.f('ix_table_allocations_reservation_id'), 'table_allocations', ['reservation_id'], unique=False)
    op.create_index(op.f('ix_table_allocations_table_id'), 'table_allocations', ['table_id'], unique=False)
    op.create_table('waitlist_entries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('earliest', sa.DateTime(timezone=True), nullable=False),
    sa.Column('latest', sa.DateTime(timezone=True), nullable=False),
    sa.Column('party_size', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('reservation_id', sa.Integer(), nullable=True),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_waitlist_entries_customer_id_customers')),
    sa.ForeignKeyConstraint(['reservation_id'], ['reservations.id'], name=op.f('fk_waitlist_entries_reservation_id_reservations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_waitlist_entries'))
    )
    op.create_index('ix_waitlist_day_status', 'waitlist_entries', ['day', 'status'], unique=False)
    op.create_table('menu_addons',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('group_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('price_paise', sa.Integer(), nullable=False),
    sa.Column('available', sa.Boolean(), nullable=False),
    sa.Column('sort', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['group_id'], ['menu_addon_groups.id'], name=op.f('fk_menu_addons_group_id_menu_addon_groups'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_menu_addons'))
    )
    op.create_index(op.f('ix_menu_addons_group_id'), 'menu_addons', ['group_id'], unique=False)
    op.create_table('order_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('menu_item_id', sa.Integer(), nullable=False),
    sa.Column('variant_id', sa.Integer(), nullable=True),
    sa.Column('item_name', sa.String(length=120), nullable=False),
    sa.Column('variant_name', sa.String(length=60), nullable=False),
    sa.Column('addons', sa.JSON(), nullable=False),
    sa.Column('unit_price_paise', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('instructions', sa.String(length=300), nullable=False),
    sa.Column('tax_rate_bp', sa.Integer(), nullable=False),
    sa.Column('prep_minutes', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['menu_item_id'], ['menu_items.id'], name=op.f('fk_order_items_menu_item_id_menu_items')),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_order_items_order_id_orders'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['variant_id'], ['menu_variants.id'], name=op.f('fk_order_items_variant_id_menu_variants'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_order_items'))
    )
    op.create_index(op.f('ix_order_items_order_id'), 'order_items', ['order_id'], unique=False)
    op.create_table('payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ref', sa.String(length=16), nullable=False),
    sa.Column('purpose', sa.String(length=16), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.Column('reservation_id', sa.Integer(), nullable=True),
    sa.Column('amount_paise', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('provider_link_id', sa.String(length=40), nullable=True),
    sa.Column('provider_payment_id', sa.String(length=40), nullable=True),
    sa.Column('short_url', sa.String(length=300), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_failure', sa.String(length=300), nullable=False),
    sa.Column('refunded_paise', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_payments_order_id_orders')),
    sa.ForeignKeyConstraint(['reservation_id'], ['reservations.id'], name=op.f('fk_payments_reservation_id_reservations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payments')),
    sa.UniqueConstraint('provider_link_id', name=op.f('uq_payments_provider_link_id')),
    sa.UniqueConstraint('ref', name=op.f('uq_payments_ref'))
    )
    op.create_index(op.f('ix_payments_order_id'), 'payments', ['order_id'], unique=False)
    op.create_index(op.f('ix_payments_reservation_id'), 'payments', ['reservation_id'], unique=False)
    op.create_index(op.f('ix_payments_status'), 'payments', ['status'], unique=False)
    op.create_table('qr_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=12), nullable=False),
    sa.Column('reservation_id', sa.Integer(), nullable=True),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('first_scanned_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('scan_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_qr_tokens_order_id_orders'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reservation_id'], ['reservations.id'], name=op.f('fk_qr_tokens_reservation_id_reservations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_qr_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_qr_tokens_token_hash'))
    )
    op.create_index(op.f('ix_qr_tokens_order_id'), 'qr_tokens', ['order_id'], unique=False)
    op.create_index(op.f('ix_qr_tokens_reservation_id'), 'qr_tokens', ['reservation_id'], unique=False)
    op.create_table('qr_scans',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('qr_id', sa.Integer(), nullable=True),
    sa.Column('scanned_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('staff_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=12), nullable=False),
    sa.Column('result', sa.String(length=24), nullable=False),
    sa.ForeignKeyConstraint(['qr_id'], ['qr_tokens.id'], name=op.f('fk_qr_scans_qr_id_qr_tokens'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_qr_scans'))
    )
    op.create_index(op.f('ix_qr_scans_qr_id'), 'qr_scans', ['qr_id'], unique=False)
    op.create_index(op.f('ix_qr_scans_scanned_at'), 'qr_scans', ['scanned_at'], unique=False)
    op.create_table('refunds',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ref', sa.String(length=16), nullable=False),
    sa.Column('payment_id', sa.Integer(), nullable=False),
    sa.Column('amount_paise', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('provider_refund_id', sa.String(length=40), nullable=True),
    sa.Column('reason', sa.String(length=200), nullable=False),
    sa.Column('error', sa.Text(), nullable=False),
    sa.Column('created_by', sa.String(length=40), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], name=op.f('fk_refunds_payment_id_payments')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refunds')),
    sa.UniqueConstraint('provider_refund_id', name=op.f('uq_refunds_provider_refund_id')),
    sa.UniqueConstraint('ref', name=op.f('uq_refunds_ref'))
    )
    op.create_index(op.f('ix_refunds_payment_id'), 'refunds', ['payment_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_refunds_payment_id'), table_name='refunds')
    op.drop_table('refunds')
    op.drop_index(op.f('ix_qr_scans_scanned_at'), table_name='qr_scans')
    op.drop_index(op.f('ix_qr_scans_qr_id'), table_name='qr_scans')
    op.drop_table('qr_scans')
    op.drop_index(op.f('ix_qr_tokens_reservation_id'), table_name='qr_tokens')
    op.drop_index(op.f('ix_qr_tokens_order_id'), table_name='qr_tokens')
    op.drop_table('qr_tokens')
    op.drop_index(op.f('ix_payments_status'), table_name='payments')
    op.drop_index(op.f('ix_payments_reservation_id'), table_name='payments')
    op.drop_index(op.f('ix_payments_order_id'), table_name='payments')
    op.drop_table('payments')
    op.drop_index(op.f('ix_order_items_order_id'), table_name='order_items')
    op.drop_table('order_items')
    op.drop_index(op.f('ix_menu_addons_group_id'), table_name='menu_addons')
    op.drop_table('menu_addons')
    op.drop_index('ix_waitlist_day_status', table_name='waitlist_entries')
    op.drop_table('waitlist_entries')
    op.drop_index(op.f('ix_table_allocations_table_id'), table_name='table_allocations')
    op.drop_index(op.f('ix_table_allocations_reservation_id'), table_name='table_allocations')
    op.drop_index(op.f('ix_table_allocations_block_id'), table_name='table_allocations')
    op.drop_table('table_allocations')
    op.drop_index(op.f('ix_orders_status'), table_name='orders')
    op.drop_index(op.f('ix_orders_customer_id'), table_name='orders')
    op.drop_index(op.f('ix_orders_created_at'), table_name='orders')
    op.drop_table('orders')
    op.drop_index(op.f('ix_messages_customer_id'), table_name='messages')
    op.drop_index(op.f('ix_messages_created_at'), table_name='messages')
    op.drop_index(op.f('ix_messages_conversation_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_menu_variants_item_id'), table_name='menu_variants')
    op.drop_table('menu_variants')
    op.drop_index(op.f('ix_menu_addon_groups_item_id'), table_name='menu_addon_groups')
    op.drop_table('menu_addon_groups')
    op.drop_index(op.f('ix_calls_started_at'), table_name='calls')
    op.drop_table('calls')
    op.drop_index(op.f('ix_table_blocks_table_id'), table_name='table_blocks')
    op.drop_table('table_blocks')
    op.drop_index(op.f('ix_staff_sessions_user_id'), table_name='staff_sessions')
    op.drop_table('staff_sessions')
    op.drop_index(op.f('ix_reservations_status'), table_name='reservations')
    op.drop_index(op.f('ix_reservations_starts_at'), table_name='reservations')
    op.drop_index(op.f('ix_reservations_customer_id'), table_name='reservations')
    op.drop_table('reservations')
    op.drop_index(op.f('ix_notifications_customer_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_created_at'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_menu_items_category_id'), table_name='menu_items')
    op.drop_table('menu_items')
    op.drop_index(op.f('ix_conversations_last_message_at'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_external_id'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_customer_id'), table_name='conversations')
    op.drop_table('conversations')
    op.drop_table('combination_tables')
    op.drop_table('callback_requests')
    op.drop_table('worker_heartbeats')
    op.drop_index(op.f('ix_webhook_events_received_at'), table_name='webhook_events')
    op.drop_table('webhook_events')
    op.drop_index(op.f('ix_usage_events_kind'), table_name='usage_events')
    op.drop_index(op.f('ix_usage_events_created_at'), table_name='usage_events')
    op.drop_table('usage_events')
    op.drop_table('table_combinations')
    op.drop_table('staff_users')
    op.drop_table('special_days')
    op.drop_table('restaurant_settings')
    op.drop_table('menu_categories')
    op.drop_index('ix_jobs_ready', table_name='jobs')
    op.drop_table('jobs')
    op.drop_table('integration_status')
    op.drop_table('dining_tables')
    op.drop_table('customers')
    op.drop_index(op.f('ix_audit_logs_created_at'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_index('ix_audit_entity', table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index(op.f('ix_alerts_created_at'), table_name='alerts')
    op.drop_table('alerts')
