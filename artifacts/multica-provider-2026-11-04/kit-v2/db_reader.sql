-- Read-only way back for the Multica provider (2026-11-04, second design).
-- One function returns only the order agent's comments on the tasks its autopilot created for one job.
-- The login role can run that function and nothing else; the function runs as a NOLOGIN owner that may read
-- only the listed columns of issue and comment. PL/pgSQL bodies are not dependency-tracked, so a Multica
-- migration is never blocked by this; if the schema changes, the function errors and the provider refuses
-- orders (no charge) until it is updated.
-- :'pw' is set by db_reader.py through stdin; it never appears on a command line.
\set ON_ERROR_STOP on
BEGIN;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'provider_ro_owner') THEN CREATE ROLE provider_ro_owner NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'multica_provider_ro') THEN CREATE ROLE multica_provider_ro LOGIN; END IF;
END $$;
ALTER ROLE multica_provider_ro WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION CONNECTION LIMIT 4 PASSWORD :'pw';
GRANT USAGE ON SCHEMA public TO provider_ro_owner;
GRANT SELECT (id, status, assignee_type, assignee_id, origin_type, origin_id, description) ON public.issue TO provider_ro_owner;
GRANT SELECT (issue_id, author_type, author_id, content, created_at, deleted_at) ON public.comment TO provider_ro_owner;
CREATE SCHEMA IF NOT EXISTS provider_ro AUTHORIZATION provider_ro_owner;
REVOKE ALL ON SCHEMA provider_ro FROM PUBLIC;
CREATE OR REPLACE FUNCTION provider_ro.order_answers(p_job text)
RETURNS TABLE(issue_status text, content text, created_at timestamptz)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
  IF p_job IS NULL OR p_job !~ '^job_[0-9a-f]{32}$' THEN
    RAISE EXCEPTION 'job id must match job_[0-9a-f]{32}';
  END IF;
  RETURN QUERY
    SELECT i.status, c.content, c.created_at
    FROM public.issue i
    LEFT JOIN public.comment c
      ON c.issue_id = i.id AND c.author_type = 'agent'
     AND c.author_id = '0ac4ba96-4066-4c8d-bfb9-690ee0c98d3e'::uuid AND c.deleted_at IS NULL
    WHERE i.origin_type = 'autopilot' AND i.origin_id = 'e06a96e6-c05f-4199-9baa-b01c8866f627'::uuid
      AND i.assignee_type = 'agent' AND i.assignee_id = '0ac4ba96-4066-4c8d-bfb9-690ee0c98d3e'::uuid
      AND i.description ~ ('"job_id":\s*"' || p_job || '"')
    ORDER BY c.created_at NULLS FIRST
    LIMIT 50;
END
$fn$;
ALTER FUNCTION provider_ro.order_answers(text) OWNER TO provider_ro_owner;
REVOKE ALL ON FUNCTION provider_ro.order_answers(text) FROM PUBLIC;
GRANT USAGE ON SCHEMA provider_ro TO multica_provider_ro;
GRANT EXECUTE ON FUNCTION provider_ro.order_answers(text) TO multica_provider_ro;
COMMIT;

-- Rollback:
-- DROP FUNCTION provider_ro.order_answers(text); DROP SCHEMA provider_ro;
-- REVOKE SELECT ON public.issue, public.comment FROM provider_ro_owner; REVOKE USAGE ON SCHEMA public FROM provider_ro_owner;
-- DROP ROLE multica_provider_ro; DROP ROLE provider_ro_owner;
