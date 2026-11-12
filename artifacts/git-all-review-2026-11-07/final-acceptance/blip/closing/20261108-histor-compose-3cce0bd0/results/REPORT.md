# HISTOR compose static check

The exact historical compose blob from commit3cce0bd0 safely parses with PyYAML6.0.2 on both gVisor hosts. The services.histor.environment.MALLOC_ARENA_MAX scalar exactly equals the configured environment-variable expression with default2. Input is bounded to64KiB and matches its native Git blob; source is unchanged.

This is static configuration validation only. No environment substitution, compose command, service startup, deployment, allocator experiment or load test was performed. No project code ran locally.
