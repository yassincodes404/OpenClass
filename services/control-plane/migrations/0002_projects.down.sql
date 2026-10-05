-- Dev-only down migration for 0002_projects.sql.
DROP TABLE IF EXISTS control_api_keys;
DROP TABLE IF EXISTS control_classifiers;
DROP TABLE IF EXISTS control_projects;
