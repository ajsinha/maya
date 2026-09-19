-- ==========================================================================
-- MAYA schema for sqlite — GENERATED from the SQLAlchemy metadata in
-- maya/persistence/models/. DO NOT EDIT BY HAND: regenerate with
--     python tools/ci/gen_schema.py
-- and CI fails the build on any drift (spec §14.3, SC-15).
-- schema-hash: 73d49a0c63a71b6eab858fae8d3a354dcb83054ee6065ba031d2eec4344fbbbe
-- ==========================================================================

CREATE TABLE access_requests (
	kind VARCHAR(24) NOT NULL, 
	object_id CHAR(36) NOT NULL, 
	object_ref VARCHAR(512) NOT NULL, 
	requester_id CHAR(36) NOT NULL, 
	level VARCHAR(16) NOT NULL, 
	reason TEXT, 
	state VARCHAR(16) NOT NULL, 
	days INTEGER NOT NULL, 
	decided_by VARCHAR(128), 
	decided_at DATETIME, 
	decision_note TEXT, 
	grant_id CHAR(36), 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_access_requests PRIMARY KEY (id)
);

CREATE INDEX ix_access_requests_object ON access_requests (kind, object_id);

CREATE INDEX ix_access_requests_requester_id ON access_requests (requester_id);

CREATE INDEX ix_access_requests_state ON access_requests (state);

CREATE TABLE anchors (
	seq BIGINT NOT NULL, 
	head_hash VARCHAR(64) NOT NULL, 
	methods JSON NOT NULL, 
	signature JSON NOT NULL, 
	tsa_token TEXT, 
	detail JSON NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_anchors PRIMARY KEY (id)
);

CREATE INDEX ix_anchors_seq ON anchors (seq);

CREATE TABLE approvals (
	object_type VARCHAR(32) NOT NULL, 
	object_id VARCHAR(64) NOT NULL, 
	round_no INTEGER NOT NULL, 
	approver VARCHAR(128) NOT NULL, 
	role VARCHAR(64) NOT NULL, 
	decision VARCHAR(16) NOT NULL, 
	rationale TEXT, 
	on_behalf_of VARCHAR(128), 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_approvals PRIMARY KEY (id)
);

CREATE INDEX ix_approvals_object ON approvals (object_type, object_id);

CREATE TABLE audit_events (
	seq INTEGER NOT NULL, 
	at DATETIME NOT NULL, 
	actor VARCHAR(128) NOT NULL, 
	principal_type VARCHAR(16) NOT NULL, 
	channel VARCHAR(16) NOT NULL, 
	action VARCHAR(64) NOT NULL, 
	object_type VARCHAR(32), 
	object_ref VARCHAR(512), 
	detail JSON NOT NULL, 
	request_id VARCHAR(64), 
	ip VARCHAR(64), 
	prev_hash VARCHAR(64) NOT NULL, 
	hash VARCHAR(64) NOT NULL, 
	CONSTRAINT pk_audit_events PRIMARY KEY (seq)
);

CREATE INDEX ix_audit_events_action ON audit_events (action);

CREATE INDEX ix_audit_events_actor ON audit_events (actor);

CREATE INDEX ix_audit_events_object_ref ON audit_events (object_ref);

CREATE TABLE blobs (
	hash VARCHAR(64) NOT NULL, 
	size BIGINT NOT NULL, 
	content_type VARCHAR(128), 
	filename VARCHAR(512), 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	CONSTRAINT pk_blobs PRIMARY KEY (hash)
);

CREATE TABLE campaigns (
	name VARCHAR(128) NOT NULL, 
	transition VARCHAR(32) NOT NULL, 
	items JSON NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	results JSON NOT NULL, 
	rationale TEXT, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_campaigns PRIMARY KEY (id)
);

CREATE TABLE challenge_memos (
	object_type VARCHAR(32) NOT NULL, 
	object_id CHAR(36) NOT NULL, 
	object_ref VARCHAR(512), 
	provider VARCHAR(32) NOT NULL, 
	model VARCHAR(64) NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	summary TEXT, 
	findings JSON NOT NULL, 
	dossier_sha256 VARCHAR(64), 
	error TEXT, 
	stance VARCHAR(16), 
	stance_by VARCHAR(128), 
	stance_note TEXT, 
	stance_at DATETIME, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_challenge_memos PRIMARY KEY (id)
);

CREATE INDEX ix_challenge_memos_object_id ON challenge_memos (object_id);

CREATE INDEX ix_challenge_memos_object_type ON challenge_memos (object_type);

CREATE TABLE comments (
	object_type VARCHAR(32) NOT NULL, 
	object_id VARCHAR(64) NOT NULL, 
	author VARCHAR(128) NOT NULL, 
	body TEXT NOT NULL, 
	blocking BOOLEAN NOT NULL, 
	resolved BOOLEAN NOT NULL, 
	anchor VARCHAR(256), 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_comments PRIMARY KEY (id)
);

CREATE INDEX ix_comments_object ON comments (object_type, object_id);

CREATE TABLE custody_events (
	warrant_type VARCHAR(16) NOT NULL, 
	warrant_id CHAR(36) NOT NULL, 
	event VARCHAR(32) NOT NULL, 
	actor VARCHAR(128) NOT NULL, 
	checksum VARCHAR(64), 
	detail JSON NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_custody_events PRIMARY KEY (id)
);

CREATE INDEX ix_custody_events_warrant_id ON custody_events (warrant_id);

CREATE TABLE delegations (
	delegator_id CHAR(36) NOT NULL, 
	delegate_id CHAR(36) NOT NULL, 
	starts_on DATE NOT NULL, 
	ends_on DATE NOT NULL, 
	object_types JSON NOT NULL, 
	reason TEXT, 
	revoked_at DATETIME, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_delegations PRIMARY KEY (id)
);

CREATE INDEX ix_delegations_delegate_id ON delegations (delegate_id);

CREATE INDEX ix_delegations_delegator_id ON delegations (delegator_id);

CREATE TABLE derivations (
	target_type VARCHAR(24) NOT NULL, 
	target_version_id CHAR(36) NOT NULL, 
	operator VARCHAR(32) NOT NULL, 
	operand_refs JSON NOT NULL, 
	options JSON NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_derivations PRIMARY KEY (id)
);

CREATE INDEX ix_derivations_target_version_id ON derivations (target_version_id);

CREATE TABLE events (
	seq INTEGER NOT NULL, 
	at DATETIME NOT NULL, 
	type VARCHAR(64) NOT NULL, 
	object_type VARCHAR(32), 
	object_ref VARCHAR(512), 
	actor VARCHAR(128) NOT NULL, 
	trace_id VARCHAR(32), 
	payload JSON NOT NULL, 
	CONSTRAINT pk_events PRIMARY KEY (seq)
);

CREATE INDEX ix_events_type ON events (type);

CREATE TABLE execution_reports (
	execution_warrant_id CHAR(36) NOT NULL, 
	environment VARCHAR(16) NOT NULL, 
	rows INTEGER NOT NULL, 
	input_stats JSON NOT NULL, 
	output_stats JSON NOT NULL, 
	breaches JSON NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_execution_reports PRIMARY KEY (id)
);

CREATE INDEX ix_execution_reports_execution_warrant_id ON execution_reports (execution_warrant_id);

CREATE TABLE fragments (
	hash VARCHAR(64) NOT NULL, 
	lake_table VARCHAR(512) NOT NULL, 
	rows BIGINT NOT NULL, 
	bytes BIGINT NOT NULL, 
	created_at DATETIME NOT NULL, 
	CONSTRAINT pk_fragments PRIMARY KEY (hash, lake_table)
);

CREATE TABLE grants (
	object_type VARCHAR(32) NOT NULL, 
	object_id VARCHAR(64) NOT NULL, 
	principal_type VARCHAR(16) NOT NULL, 
	principal_id VARCHAR(128) NOT NULL, 
	level VARCHAR(16) NOT NULL, 
	deny BOOLEAN NOT NULL, 
	expires_at DATETIME, 
	conditions JSON NOT NULL, 
	inert_reason TEXT, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_grants PRIMARY KEY (id)
);

CREATE INDEX ix_grants_object ON grants (object_type, object_id);

CREATE TABLE groups (
	name VARCHAR(128) NOT NULL, 
	description TEXT, 
	sso_claim VARCHAR(256), 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_groups PRIMARY KEY (id), 
	CONSTRAINT uq_groups_name UNIQUE (name)
);

CREATE TABLE holdout_scores (
	training_warrant_id CHAR(36) NOT NULL, 
	parameter_set_id CHAR(36), 
	attempt_no INTEGER NOT NULL, 
	metrics JSON NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_holdout_scores PRIMARY KEY (id)
);

CREATE INDEX ix_holdout_scores_training_warrant_id ON holdout_scores (training_warrant_id);

CREATE TABLE inheritance_links (
	child_type VARCHAR(24) NOT NULL, 
	child_version_id CHAR(36) NOT NULL, 
	parent_ref VARCHAR(512) NOT NULL, 
	binding VARCHAR(16) NOT NULL, 
	override_diff JSON NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_inheritance_links PRIMARY KEY (id), 
	CONSTRAINT uq_inheritance_links_child_version_id UNIQUE (child_version_id)
);

CREATE TABLE jobs (
	job_type VARCHAR(48) NOT NULL, 
	owner VARCHAR(128) NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	params JSON NOT NULL, 
	params_hash VARCHAR(64) NOT NULL, 
	idempotency_key VARCHAR(128), 
	progress INTEGER NOT NULL, 
	message TEXT, 
	result JSON NOT NULL, 
	error TEXT, 
	attempts INTEGER NOT NULL, 
	max_attempts INTEGER NOT NULL, 
	run_after DATETIME, 
	started_at DATETIME, 
	finished_at DATETIME, 
	cancel_requested BOOLEAN NOT NULL, 
	trace_id VARCHAR(32) NOT NULL, 
	logs JSON NOT NULL, 
	worker VARCHAR(128), 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_jobs PRIMARY KEY (id), 
	CONSTRAINT uq_jobs_idempotency_key UNIQUE (idempotency_key)
);

CREATE INDEX ix_jobs_owner ON jobs (owner);

CREATE INDEX ix_jobs_state_run_after ON jobs (state, run_after);

CREATE TABLE lineage_edges (
	src_ref VARCHAR(512) NOT NULL, 
	dst_ref VARCHAR(512) NOT NULL, 
	edge_type VARCHAR(32) NOT NULL, 
	label VARCHAR(256), 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_lineage_edges PRIMARY KEY (id), 
	CONSTRAINT uq_lineage_edges_src_ref_dst_ref_edge_type UNIQUE (src_ref, dst_ref, edge_type)
);

CREATE INDEX ix_lineage_edges_dst_ref ON lineage_edges (dst_ref);

CREATE INDEX ix_lineage_edges_src_ref ON lineage_edges (src_ref);

CREATE TABLE notifications (
	user_id CHAR(36) NOT NULL, 
	kind VARCHAR(32) NOT NULL, 
	message TEXT NOT NULL, 
	object_ref VARCHAR(512), 
	read_at DATETIME, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_notifications PRIMARY KEY (id)
);

CREATE INDEX ix_notifications_user_id ON notifications (user_id);

CREATE TABLE restore_drills (
	performed_at DATETIME NOT NULL, 
	backup_taken_at DATETIME, 
	dialect VARCHAR(16) NOT NULL, 
	outcome VARCHAR(16) NOT NULL, 
	pins_checked INTEGER NOT NULL, 
	drift INTEGER NOT NULL, 
	audit_chain_ok BOOLEAN NOT NULL, 
	anchors_ok BOOLEAN NOT NULL, 
	duration_seconds FLOAT NOT NULL, 
	verified_by VARCHAR(128) NOT NULL, 
	notes TEXT, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_restore_drills PRIMARY KEY (id)
);

CREATE INDEX ix_restore_drills_performed_at ON restore_drills (performed_at);

CREATE TABLE roles (
	name VARCHAR(64) NOT NULL, 
	description TEXT, 
	capabilities JSON NOT NULL, 
	builtin BOOLEAN NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_roles PRIMARY KEY (id), 
	CONSTRAINT uq_roles_name UNIQUE (name)
);

CREATE TABLE schema_meta (
	"key" VARCHAR(64) NOT NULL, 
	value TEXT NOT NULL, 
	CONSTRAINT pk_schema_meta PRIMARY KEY ("key")
);

CREATE TABLE search_terms (
	id INTEGER NOT NULL, 
	term VARCHAR(64) NOT NULL, 
	kind VARCHAR(24) NOT NULL, 
	object_id CHAR(36) NOT NULL, 
	field VARCHAR(16) NOT NULL, 
	weight INTEGER NOT NULL, 
	CONSTRAINT pk_search_terms PRIMARY KEY (id)
);

CREATE INDEX ix_search_terms_object_id ON search_terms (object_id);

CREATE INDEX ix_search_terms_term ON search_terms (term);

CREATE TABLE sql_connections (
	name VARCHAR(128) NOT NULL, 
	url VARCHAR(1024) NOT NULL, 
	password_env VARCHAR(128), 
	description TEXT, 
	options JSON NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_sql_connections PRIMARY KEY (id), 
	CONSTRAINT uq_sql_connections_name UNIQUE (name)
);

CREATE TABLE subscriptions (
	user_id CHAR(36) NOT NULL, 
	object_ref VARCHAR(512) NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_subscriptions PRIMARY KEY (id), 
	CONSTRAINT uq_subscriptions_user_id_object_ref UNIQUE (user_id, object_ref)
);

CREATE TABLE users (
	username VARCHAR(128) NOT NULL, 
	email VARCHAR(256), 
	display_name VARCHAR(256), 
	auth_source VARCHAR(16) NOT NULL, 
	password_hash TEXT, 
	status VARCHAR(16) NOT NULL, 
	must_change_password BOOLEAN NOT NULL, 
	failed_attempts INTEGER NOT NULL, 
	first_failed_at DATETIME, 
	locked_until DATETIME, 
	last_login_at DATETIME, 
	password_changed_at DATETIME, 
	mfa_enabled BOOLEAN NOT NULL, 
	mfa_secret TEXT, 
	mfa_last_step BIGINT, 
	external_subject VARCHAR(256), 
	is_service BOOLEAN NOT NULL, 
	desk VARCHAR(128), 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_users PRIMARY KEY (id), 
	CONSTRAINT uq_users_username UNIQUE (username)
);

CREATE INDEX ix_users_external_subject ON users (external_subject);

CREATE TABLE webhook_deliveries (
	webhook_id CHAR(36) NOT NULL, 
	event_seq BIGINT NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	attempts INTEGER NOT NULL, 
	next_attempt_at DATETIME, 
	last_status INTEGER, 
	last_error TEXT, 
	delivered_at DATETIME, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_webhook_deliveries PRIMARY KEY (id)
);

CREATE INDEX ix_webhook_deliveries_due ON webhook_deliveries (state, next_attempt_at);

CREATE INDEX ix_webhook_deliveries_webhook_id ON webhook_deliveries (webhook_id);

CREATE TABLE webhooks (
	name VARCHAR(128) NOT NULL, 
	url VARCHAR(1024) NOT NULL, 
	secret_sealed TEXT NOT NULL, 
	event_types JSON NOT NULL, 
	active BOOLEAN NOT NULL, 
	description TEXT, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_webhooks PRIMARY KEY (id), 
	CONSTRAINT uq_webhooks_name UNIQUE (name)
);

CREATE TABLE workflow_events (
	object_type VARCHAR(32) NOT NULL, 
	object_id VARCHAR(64) NOT NULL, 
	object_ref VARCHAR(512), 
	transition VARCHAR(32) NOT NULL, 
	from_state VARCHAR(24) NOT NULL, 
	to_state VARCHAR(24) NOT NULL, 
	actor VARCHAR(128) NOT NULL, 
	rationale TEXT, 
	forced BOOLEAN NOT NULL, 
	policy_id CHAR(36), 
	checks JSON NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_workflow_events PRIMARY KEY (id)
);

CREATE INDEX ix_workflow_events_object ON workflow_events (object_type, object_id);

CREATE TABLE workflow_policies (
	object_type VARCHAR(32) NOT NULL, 
	scope VARCHAR(128) NOT NULL, 
	version_no INTEGER NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	policy JSON NOT NULL, 
	note TEXT, 
	approved_by VARCHAR(128), 
	activated_at DATETIME, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_workflow_policies PRIMARY KEY (id), 
	CONSTRAINT uq_workflow_policies_object_type_scope_version_no UNIQUE (object_type, scope, version_no)
);

CREATE TABLE workspace_changes (
	workspace_id CHAR(36) NOT NULL, 
	object_kind VARCHAR(16) NOT NULL, 
	object_id CHAR(36) NOT NULL, 
	object_ref VARCHAR(512) NOT NULL, 
	base_version_id CHAR(36) NOT NULL, 
	base_version_no INTEGER NOT NULL, 
	definition JSON NOT NULL, 
	note TEXT, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_workspace_changes PRIMARY KEY (id), 
	CONSTRAINT uq_workspace_changes_workspace_id_object_kind_object_id UNIQUE (workspace_id, object_kind, object_id)
);

CREATE INDEX ix_workspace_changes_workspace_id ON workspace_changes (workspace_id);

CREATE TABLE workspaces (
	name VARCHAR(128) NOT NULL, 
	owner_id CHAR(36) NOT NULL, 
	description TEXT, 
	state VARCHAR(16) NOT NULL, 
	replay JSON NOT NULL, 
	submitted_versions JSON NOT NULL, 
	submitted_at DATETIME, 
	merged_at DATETIME, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_workspaces PRIMARY KEY (id)
);

CREATE INDEX ix_workspaces_owner_id ON workspaces (owner_id);

CREATE TABLE api_keys (
	key_id VARCHAR(32) NOT NULL, 
	user_id CHAR(36) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	env VARCHAR(8) NOT NULL, 
	secret_hash TEXT NOT NULL, 
	roles JSON NOT NULL, 
	namespaces JSON NOT NULL, 
	actions JSON NOT NULL, 
	cidrs JSON NOT NULL, 
	expires_at DATETIME NOT NULL, 
	last_used_at DATETIME, 
	revoked_at DATETIME, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_api_keys PRIMARY KEY (id), 
	CONSTRAINT uq_api_keys_key_id UNIQUE (key_id), 
	CONSTRAINT fk_api_keys_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_api_keys_user_id ON api_keys (user_id);

CREATE TABLE auth_challenges (
	kind VARCHAR(32) NOT NULL, 
	handle VARCHAR(256) NOT NULL, 
	user_id CHAR(36), 
	session_id CHAR(36), 
	expires_at DATETIME NOT NULL, 
	consumed_at DATETIME, 
	detail JSON NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_auth_challenges PRIMARY KEY (id), 
	CONSTRAINT uq_auth_challenges_handle UNIQUE (handle), 
	CONSTRAINT fk_auth_challenges_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_auth_challenges_expires_at ON auth_challenges (expires_at);

CREATE INDEX ix_auth_challenges_kind ON auth_challenges (kind);

CREATE INDEX ix_auth_challenges_user_id ON auth_challenges (user_id);

CREATE TABLE group_members (
	group_id CHAR(36) NOT NULL, 
	user_id CHAR(36) NOT NULL, 
	CONSTRAINT pk_group_members PRIMARY KEY (group_id, user_id), 
	CONSTRAINT fk_group_members_group_id_groups FOREIGN KEY(group_id) REFERENCES groups (id), 
	CONSTRAINT fk_group_members_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE group_roles (
	group_id CHAR(36) NOT NULL, 
	role_id CHAR(36) NOT NULL, 
	CONSTRAINT pk_group_roles PRIMARY KEY (group_id, role_id), 
	CONSTRAINT fk_group_roles_group_id_groups FOREIGN KEY(group_id) REFERENCES groups (id), 
	CONSTRAINT fk_group_roles_role_id_roles FOREIGN KEY(role_id) REFERENCES roles (id)
);

CREATE TABLE namespaces (
	name VARCHAR(128) NOT NULL, 
	parent_id CHAR(36), 
	description TEXT, 
	default_visibility VARCHAR(32) NOT NULL, 
	quota_bytes BIGINT, 
	sod VARCHAR(16) NOT NULL, 
	preset VARCHAR(16) NOT NULL, 
	classification VARCHAR(16) NOT NULL, 
	is_scratch BOOLEAN NOT NULL, 
	production BOOLEAN NOT NULL, 
	owner_id CHAR(36), 
	materialize_policy VARCHAR(16) NOT NULL, 
	shadow_materiality FLOAT, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_namespaces PRIMARY KEY (id), 
	CONSTRAINT uq_namespaces_name UNIQUE (name), 
	CONSTRAINT fk_namespaces_parent_id_namespaces FOREIGN KEY(parent_id) REFERENCES namespaces (id), 
	CONSTRAINT fk_namespaces_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE TABLE sessions (
	user_id CHAR(36) NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	channel VARCHAR(16) NOT NULL, 
	mfa_state VARCHAR(16) NOT NULL, 
	auth_method VARCHAR(16) NOT NULL, 
	last_seen_at DATETIME, 
	expires_at DATETIME NOT NULL, 
	absolute_expires_at DATETIME NOT NULL, 
	revoked_at DATETIME, 
	ip VARCHAR(64), 
	user_agent VARCHAR(512), 
	sso_name_id VARCHAR(512), 
	sso_session_index VARCHAR(256), 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_sessions PRIMARY KEY (id), 
	CONSTRAINT fk_sessions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT uq_sessions_token_hash UNIQUE (token_hash)
);

CREATE INDEX ix_sessions_sso_name_id ON sessions (sso_name_id);

CREATE INDEX ix_sessions_user_id ON sessions (user_id);

CREATE TABLE user_roles (
	user_id CHAR(36) NOT NULL, 
	role_id CHAR(36) NOT NULL, 
	CONSTRAINT pk_user_roles PRIMARY KEY (user_id, role_id), 
	CONSTRAINT fk_user_roles_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT fk_user_roles_role_id_roles FOREIGN KEY(role_id) REFERENCES roles (id)
);

CREATE TABLE webauthn_credentials (
	user_id CHAR(36) NOT NULL, 
	credential_id VARCHAR(512) NOT NULL, 
	public_key TEXT NOT NULL, 
	sign_count BIGINT NOT NULL, 
	transports JSON NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	aaguid VARCHAR(64), 
	backed_up BOOLEAN NOT NULL, 
	last_used_at DATETIME, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_webauthn_credentials PRIMARY KEY (id), 
	CONSTRAINT fk_webauthn_credentials_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT uq_webauthn_credentials_credential_id UNIQUE (credential_id)
);

CREATE INDEX ix_webauthn_credentials_user_id ON webauthn_credentials (user_id);

CREATE TABLE feature_sets (
	namespace_id CHAR(36) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	owner_id CHAR(36) NOT NULL, 
	description TEXT, 
	tags JSON NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_feature_sets PRIMARY KEY (id), 
	CONSTRAINT uq_feature_sets_namespace_id_name UNIQUE (namespace_id, name), 
	CONSTRAINT fk_feature_sets_namespace_id_namespaces FOREIGN KEY(namespace_id) REFERENCES namespaces (id), 
	CONSTRAINT fk_feature_sets_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE INDEX ix_feature_sets_namespace_id ON feature_sets (namespace_id);

CREATE TABLE features (
	namespace_id CHAR(36) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	owner_id CHAR(36) NOT NULL, 
	description TEXT, 
	tags JSON NOT NULL, 
	index_spec JSON NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	ungoverned BOOLEAN NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_features PRIMARY KEY (id), 
	CONSTRAINT uq_features_namespace_id_name UNIQUE (namespace_id, name), 
	CONSTRAINT fk_features_namespace_id_namespaces FOREIGN KEY(namespace_id) REFERENCES namespaces (id), 
	CONSTRAINT fk_features_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE INDEX ix_features_namespace_id ON features (namespace_id);

CREATE TABLE models (
	namespace_id CHAR(36) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	owner_id CHAR(36) NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	description TEXT, 
	tags JSON NOT NULL, 
	vendor JSON NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_models PRIMARY KEY (id), 
	CONSTRAINT uq_models_namespace_id_name UNIQUE (namespace_id, name), 
	CONSTRAINT fk_models_namespace_id_namespaces FOREIGN KEY(namespace_id) REFERENCES namespaces (id), 
	CONSTRAINT fk_models_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE INDEX ix_models_namespace_id ON models (namespace_id);

CREATE TABLE feature_ingests (
	feature_id CHAR(36) NOT NULL, 
	blob_hash VARCHAR(64), 
	source_type VARCHAR(16) NOT NULL, 
	knowledge_time DATETIME NOT NULL, 
	rows BIGINT NOT NULL, 
	lake_version INTEGER, 
	note TEXT, 
	restatement BOOLEAN NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_feature_ingests PRIMARY KEY (id), 
	CONSTRAINT fk_feature_ingests_feature_id_features FOREIGN KEY(feature_id) REFERENCES features (id)
);

CREATE INDEX ix_feature_ingests_feature_id ON feature_ingests (feature_id);

CREATE TABLE feature_set_versions (
	feature_set_id CHAR(36) NOT NULL, 
	version_no INTEGER NOT NULL, 
	state VARCHAR(24) NOT NULL, 
	definition JSON NOT NULL, 
	definition_hash VARCHAR(64), 
	change_class VARCHAR(16), 
	non_causal BOOLEAN NOT NULL, 
	force_approved BOOLEAN NOT NULL, 
	submitted_at DATETIME, 
	submitted_by VARCHAR(128), 
	approved_at DATETIME, 
	approved_by VARCHAR(128), 
	needs_reapproval TEXT, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_feature_set_versions PRIMARY KEY (id), 
	CONSTRAINT uq_feature_set_versions_feature_set_id_version_no UNIQUE (feature_set_id, version_no), 
	CONSTRAINT fk_feature_set_versions_feature_set_id_feature_sets FOREIGN KEY(feature_set_id) REFERENCES feature_sets (id)
);

CREATE INDEX ix_feature_set_versions_definition_hash ON feature_set_versions (definition_hash);

CREATE INDEX ix_feature_set_versions_feature_set_id ON feature_set_versions (feature_set_id);

CREATE TABLE feature_versions (
	feature_id CHAR(36) NOT NULL, 
	version_no INTEGER NOT NULL, 
	state VARCHAR(24) NOT NULL, 
	definition JSON NOT NULL, 
	definition_hash VARCHAR(64), 
	change_class VARCHAR(16), 
	non_causal BOOLEAN NOT NULL, 
	force_approved BOOLEAN NOT NULL, 
	submitted_at DATETIME, 
	submitted_by VARCHAR(128), 
	approved_at DATETIME, 
	approved_by VARCHAR(128), 
	needs_reapproval TEXT, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_feature_versions PRIMARY KEY (id), 
	CONSTRAINT uq_feature_versions_feature_id_version_no UNIQUE (feature_id, version_no), 
	CONSTRAINT fk_feature_versions_feature_id_features FOREIGN KEY(feature_id) REFERENCES features (id)
);

CREATE INDEX ix_feature_versions_definition_hash ON feature_versions (definition_hash);

CREATE INDEX ix_feature_versions_feature_id ON feature_versions (feature_id);

CREATE TABLE model_versions (
	model_id CHAR(36) NOT NULL, 
	version_no INTEGER NOT NULL, 
	state VARCHAR(24) NOT NULL, 
	maturity VARCHAR(16) NOT NULL, 
	formula_ir JSON NOT NULL, 
	input_contract JSON NOT NULL, 
	ir_hash VARCHAR(64), 
	artifact_hash VARCHAR(64), 
	artifact_report JSON NOT NULL, 
	spec_latex TEXT, 
	spec_state JSON NOT NULL, 
	definition_hash VARCHAR(64), 
	opaque BOOLEAN NOT NULL, 
	successor_ref VARCHAR(512), 
	force_approved BOOLEAN NOT NULL, 
	submitted_at DATETIME, 
	submitted_by VARCHAR(128), 
	approved_at DATETIME, 
	approved_by VARCHAR(128), 
	needs_reapproval TEXT, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_model_versions PRIMARY KEY (id), 
	CONSTRAINT uq_model_versions_model_id_version_no UNIQUE (model_id, version_no), 
	CONSTRAINT fk_model_versions_model_id_models FOREIGN KEY(model_id) REFERENCES models (id)
);

CREATE INDEX ix_model_versions_model_id ON model_versions (model_id);

CREATE TABLE composite_members (
	id CHAR(36) NOT NULL, 
	composite_version_id CHAR(36) NOT NULL, 
	alias VARCHAR(64) NOT NULL, 
	member_ref VARCHAR(512) NOT NULL, 
	binding VARCHAR(16) NOT NULL, 
	frozen BOOLEAN NOT NULL, 
	borrowed_parameter_set_id CHAR(36), 
	order_no INTEGER NOT NULL, 
	CONSTRAINT pk_composite_members PRIMARY KEY (id), 
	CONSTRAINT uq_composite_members_composite_version_id_alias UNIQUE (composite_version_id, alias), 
	CONSTRAINT fk_composite_members_composite_version_id_model_versions FOREIGN KEY(composite_version_id) REFERENCES model_versions (id)
);

CREATE INDEX ix_composite_members_composite_version_id ON composite_members (composite_version_id);

CREATE TABLE execution_warrants (
	namespace_id CHAR(36) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	version_no INTEGER NOT NULL, 
	state VARCHAR(24) NOT NULL, 
	owner_id CHAR(36) NOT NULL, 
	training_warrant_id CHAR(36), 
	model_version_id CHAR(36) NOT NULL, 
	parameter_set_id CHAR(36), 
	spec JSON NOT NULL, 
	manifest JSON NOT NULL, 
	backends JSON NOT NULL, 
	valid_from DATETIME, 
	valid_to DATETIME, 
	sealed_at DATETIME, 
	suspended_at DATETIME, 
	suspend_reason TEXT, 
	revoked_at DATETIME, 
	revoke_reason TEXT, 
	executions INTEGER NOT NULL, 
	force_approved BOOLEAN NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_execution_warrants PRIMARY KEY (id), 
	CONSTRAINT uq_execution_warrants_namespace_id_name_version_no UNIQUE (namespace_id, name, version_no), 
	CONSTRAINT fk_execution_warrants_namespace_id_namespaces FOREIGN KEY(namespace_id) REFERENCES namespaces (id), 
	CONSTRAINT fk_execution_warrants_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id), 
	CONSTRAINT fk_execution_warrants_model_version_id_model_versions FOREIGN KEY(model_version_id) REFERENCES model_versions (id)
);

CREATE INDEX ix_execution_warrants_namespace_id ON execution_warrants (namespace_id);

CREATE TABLE feature_pins (
	feature_id CHAR(36) NOT NULL, 
	feature_version_id CHAR(36) NOT NULL, 
	pin_name VARCHAR(128) NOT NULL, 
	as_of_date DATE NOT NULL, 
	as_of_known DATETIME NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	content_hash VARCHAR(64), 
	schema_digest VARCHAR(64), 
	fragments JSON NOT NULL, 
	lake_table VARCHAR(512), 
	row_count BIGINT NOT NULL, 
	bytes_total BIGINT NOT NULL, 
	bytes_new BIGINT NOT NULL, 
	fill_report JSON NOT NULL, 
	quality JSON NOT NULL, 
	provenance JSON NOT NULL, 
	sealed_at DATETIME, 
	retired_at DATETIME, 
	retire_reason TEXT, 
	failure TEXT, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_feature_pins PRIMARY KEY (id), 
	CONSTRAINT uq_feature_pins_feature_id_pin_name_as_of_date UNIQUE (feature_id, pin_name, as_of_date), 
	CONSTRAINT fk_feature_pins_feature_id_features FOREIGN KEY(feature_id) REFERENCES features (id), 
	CONSTRAINT fk_feature_pins_feature_version_id_feature_versions FOREIGN KEY(feature_version_id) REFERENCES feature_versions (id)
);

CREATE INDEX ix_feature_pins_feature_id ON feature_pins (feature_id);

CREATE TABLE feature_set_members (
	id CHAR(36) NOT NULL, 
	feature_set_version_id CHAR(36) NOT NULL, 
	attr_name VARCHAR(128) NOT NULL, 
	ref_uri VARCHAR(512) NOT NULL, 
	source_attr VARCHAR(128) NOT NULL, 
	"cast" VARCHAR(64), 
	overrides JSON NOT NULL, 
	order_no INTEGER NOT NULL, 
	CONSTRAINT pk_feature_set_members PRIMARY KEY (id), 
	CONSTRAINT fk_feature_set_members_feature_set_version_id_feature_set_versions FOREIGN KEY(feature_set_version_id) REFERENCES feature_set_versions (id)
);

CREATE INDEX ix_feature_set_members_feature_set_version_id ON feature_set_members (feature_set_version_id);

CREATE TABLE feature_set_pins (
	feature_set_id CHAR(36) NOT NULL, 
	feature_set_version_id CHAR(36) NOT NULL, 
	pin_name VARCHAR(128) NOT NULL, 
	as_of_date DATE NOT NULL, 
	as_of_known DATETIME NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	member_pin_ids JSON NOT NULL, 
	content_hash VARCHAR(64), 
	schema_digest VARCHAR(64), 
	fragments JSON NOT NULL, 
	lake_table VARCHAR(512), 
	manifest JSON NOT NULL, 
	row_count BIGINT NOT NULL, 
	bytes_total BIGINT NOT NULL, 
	bytes_new BIGINT NOT NULL, 
	provenance JSON NOT NULL, 
	sealed_at DATETIME, 
	retired_at DATETIME, 
	retire_reason TEXT, 
	failure TEXT, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_feature_set_pins PRIMARY KEY (id), 
	CONSTRAINT uq_feature_set_pins_feature_set_id_pin_name_as_of_date UNIQUE (feature_set_id, pin_name, as_of_date), 
	CONSTRAINT fk_feature_set_pins_feature_set_id_feature_sets FOREIGN KEY(feature_set_id) REFERENCES feature_sets (id), 
	CONSTRAINT fk_feature_set_pins_feature_set_version_id_feature_set_versions FOREIGN KEY(feature_set_version_id) REFERENCES feature_set_versions (id)
);

CREATE INDEX ix_feature_set_pins_feature_set_id ON feature_set_pins (feature_set_id);

CREATE TABLE parameter_sets (
	model_version_id CHAR(36) NOT NULL, 
	training_warrant_id CHAR(36), 
	name VARCHAR(128) NOT NULL, 
	state VARCHAR(24) NOT NULL, 
	"values" JSON NOT NULL, 
	values_hash VARCHAR(64) NOT NULL, 
	param_schema JSON NOT NULL, 
	metrics JSON NOT NULL, 
	data_checksum VARCHAR(64), 
	verified_data BOOLEAN NOT NULL, 
	unverified_justification TEXT, 
	member_alias VARCHAR(64), 
	notes TEXT, 
	force_approved BOOLEAN NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_parameter_sets PRIMARY KEY (id), 
	CONSTRAINT fk_parameter_sets_model_version_id_model_versions FOREIGN KEY(model_version_id) REFERENCES model_versions (id)
);

CREATE INDEX ix_parameter_sets_model_version_id ON parameter_sets (model_version_id);

CREATE INDEX ix_parameter_sets_training_warrant_id ON parameter_sets (training_warrant_id);

CREATE TABLE training_warrants (
	namespace_id CHAR(36) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	version_no INTEGER NOT NULL, 
	state VARCHAR(24) NOT NULL, 
	owner_id CHAR(36) NOT NULL, 
	model_version_id CHAR(36) NOT NULL, 
	featureset_ref VARCHAR(512) NOT NULL, 
	feature_set_pin_id CHAR(36), 
	spec JSON NOT NULL, 
	contract_report JSON NOT NULL, 
	leakage_certificate JSON NOT NULL, 
	backends JSON NOT NULL, 
	expires_at DATETIME, 
	sealed_at DATETIME, 
	revoked_at DATETIME, 
	revoke_reason TEXT, 
	clone_of CHAR(36), 
	holdout_attempts INTEGER NOT NULL, 
	holdout_hash VARCHAR(64), 
	holdout_rows INTEGER, 
	force_approved BOOLEAN NOT NULL, 
	id CHAR(36) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR(128), 
	updated_at DATETIME NOT NULL, 
	updated_by VARCHAR(128), 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_training_warrants PRIMARY KEY (id), 
	CONSTRAINT uq_training_warrants_namespace_id_name_version_no UNIQUE (namespace_id, name, version_no), 
	CONSTRAINT fk_training_warrants_namespace_id_namespaces FOREIGN KEY(namespace_id) REFERENCES namespaces (id), 
	CONSTRAINT fk_training_warrants_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id), 
	CONSTRAINT fk_training_warrants_model_version_id_model_versions FOREIGN KEY(model_version_id) REFERENCES model_versions (id)
);

CREATE INDEX ix_training_warrants_namespace_id ON training_warrants (namespace_id);

CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;

CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;

