"""The helpers behind the sandbox routes, one module per area. ``web.backend.api.sandbox`` keeps
the routes and the shared state (the active-sandbox registry, locks, the sweeper) and
re-exports every name here. This code reads that module's state and helpers at call time
(``sandbox_api.<name>``), so a value set or patched there reaches it.
"""
