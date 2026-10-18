-- Cria as roles e a base de dados do Sentinel-AI na instância PostgreSQL local.
-- Executar como superutilizador local (as passwords vêm do .env, nunca da linha de comandos):
--   ./scripts/db_bootstrap.sh
-- Idempotente: pode ser reexecutado sem erro (atualiza as passwords).

SELECT format('CREATE ROLE %I LOGIN', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
\gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'app_user', :'app_password')
\gexec

SELECT format('CREATE ROLE %I LOGIN', :'ro_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'ro_user')
\gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'ro_user', :'ro_password')
\gexec

SELECT format('CREATE DATABASE %I OWNER %I ENCODING ''UTF8''', :'db_name', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db_name')
\gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db_name', :'ro_user')
\gexec
