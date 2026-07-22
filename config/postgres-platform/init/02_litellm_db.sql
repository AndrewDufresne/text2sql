-- Create a dedicated database for LiteLLM Admin UI (key/team/user mgmt).
-- Runs only on first boot of the postgres-platform volume.
SELECT 'CREATE DATABASE litellm OWNER ' || current_user
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'litellm')\gexec
