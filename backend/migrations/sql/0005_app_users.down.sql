SET search_path = finpilot, public;

DROP POLICY IF EXISTS role_catalog_read ON role_catalog;
DROP POLICY IF EXISTS app_users_self_select ON app_users;
DROP TABLE IF EXISTS app_users;
DROP TABLE IF EXISTS role_catalog;
