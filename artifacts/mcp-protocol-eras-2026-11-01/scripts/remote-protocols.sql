-- Latest successful read of every listed remote server (streamable-http or sse) between 2026-10-25 and the as-of time,
-- with the protocol version that read negotiated. Read-only; HISTOR prod Postgres.
SET statement_timeout = '300s';
SET default_transaction_read_only = on;
COPY (
  SELECT DISTINCT ON (o.target_id)
         o.target_id AS server_id, t.name, t.endpoint, t.transport, o.observed_at AS last_ok_at,
         o.protocol AS protocol_version, o.tool_count, o.server_name, o.server_version
  FROM observations o JOIN targets t ON t.id = o.target_id
  WHERE t.transport <> 'stdio' AND t.delisted = 0 AND o.status = 'ok'
    AND o.observed_at >= '2026-10-25T00:00:00Z' AND o.observed_at <= '2026-11-01T09:15:00Z'
  ORDER BY o.target_id, o.observed_at DESC
) TO STDOUT WITH (FORMAT csv, HEADER);
