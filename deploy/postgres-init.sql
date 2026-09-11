-- MAYA — the two roles a deployment needs, and why they are two.
--
-- The schema is applied by an OWNER. The application connects as somebody
-- else, and owns nothing.
--
-- This is not tidiness. `FORCE ROW LEVEL SECURITY` binds the table owner, but
-- a table's owner is whoever ran the DDL — so a deployment where the
-- application owns its own tables has policies that bind nobody, and a
-- configuration that looks entirely correct. The second role is what gives the
-- backstop something to act on.
--
-- One level below that: a SUPERUSER bypasses row-level security altogether,
-- FORCE or not. Neither role here is one, and `GET /api/v1/row-level-security`
-- reports the connecting role's exemption precisely because that fact decides
-- whether any of the rest of it is true.

CREATE ROLE maya_app NOLOGIN;

CREATE ROLE maya_app_login LOGIN PASSWORD 'maya_app_password' IN ROLE maya_app;

GRANT USAGE ON SCHEMA public TO maya_app;

-- Applies to tables created LATER by the owner, which is every table: the
-- schema is applied at first start-up, after this file has run.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO maya_app;

-- Deliberately NOT granted: CREATE on the schema, and ownership of anything.
-- An application that can create a table can create one without a policy.
