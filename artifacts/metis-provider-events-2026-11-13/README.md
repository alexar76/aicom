# METIS Tavily telemetry canary

The candidate image `sha256:936472c205acbecc9a4b915a9941a0604d12832705ebb454f8ce0c53a0fe8e65` layers the three telemetry modules over the live `0.2.6` image. The isolated checks preserved all 143 knowledge entries and passed the authorization regression suite. A network-disabled fixture recorded one Tavily success and one Tavily failure. A DuckDuckGo fallback in the second request returned results to the caller while the event still described Tavily's failure. Event bodies contain fixed labels and a random UUID. [Canary receipt](canary.jsonl)

The first run completed the runtime probes and failed to read the telemetry fixture's multiline diagnostic output as a single JSON object. The second run parsed the final JSON line and completed all checks.

The production service has no configured ALIEN Monitor URL or token. Automatic review rejected provisioning the scoped write credential on the METIS host because the credential transfer and persistence require explicit approval. The canary and rollback preparation are ready on the METIS host. The service remains on the verified baseline image.
