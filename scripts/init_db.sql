-- AEGIS Database Initialization
-- Creates schemas and extensions for Flask/Django migration

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- Full-text search
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- Advanced indexing
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- UUID generation

-- Create schemas
CREATE SCHEMA IF NOT EXISTS flask;  -- Legacy Flask tables
CREATE SCHEMA IF NOT EXISTS django;  -- New Django tables

-- Grant privileges to aegis_user
GRANT ALL ON SCHEMA flask TO aegis_user;
GRANT ALL ON SCHEMA django TO aegis_user;
GRANT ALL ON SCHEMA public TO aegis_user;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA flask GRANT ALL ON TABLES TO aegis_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA django GRANT ALL ON TABLES TO aegis_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO aegis_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA flask GRANT ALL ON SEQUENCES TO aegis_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA django GRANT ALL ON SEQUENCES TO aegis_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO aegis_user;

-- Create FHIR database for HAPI FHIR Server
CREATE DATABASE fhir OWNER aegis_user;

-- Comment for documentation
COMMENT ON SCHEMA flask IS 'Legacy Flask application tables (during migration)';
COMMENT ON SCHEMA django IS 'New Django application tables';
