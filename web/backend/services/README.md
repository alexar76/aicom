# Services Boundaries

Service modules are grouped by responsibility to reduce architectural drift:

- `domain_*`, `spec_*`, `catalog_*`, `commerce_*`: business/domain logic
- `*_loader`, `learning_memory`, `security_report_loader`: infrastructure/data access helpers
- `*_quality`, `quality_constitution`, `release_cockpit`: quality policy and gates
- `feedback_*`, `telemetry_*`: user-signal ingestion and synthesis

Rules:

1. Domain modules should not import UI/router modules.
2. Infrastructure helpers should stay side-effect focused (I/O, persistence, adapters).
3. Quality gates may read domain/infrastructure outputs, but should not mutate core business state directly.
