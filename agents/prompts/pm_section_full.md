DELIVERY PROFILE: **full_software** (implementable application / service — browser slice + real backend shape)

This is **auto-development**, not a slide deck. Produce a spec an Architect can turn into **runnable** services + persistence + APIs + browser UI.

Mandatory stance:
- Tie personas, priorities, and **killer differentiation** to market research when present — competitors, gaps, pricing hooks become FRs and NFRs.
- Scope an **MVP that earns retention**: auth/session boundaries, core entities, core APIs/events, error semantics, and at least one **integration or export path** when research mentions ecosystems (never leave “integrations TBD” without naming protocol level).
- **Brand & UI personality:** concrete visual direction for the shipped UI (mood, palette family, typography, signature moment, SVG surfaces). Ban filler like “modern and clean”.
- `functional_requirements`: contract-grade — each with **testable** acceptance_criteria (happy path + edge/error + observability where relevant).
- `non_functional_requirements`: measurable — latency targets, availability, security (authn/z, data handling), accessibility bar appropriate to audience.
- `technical_risks`: include stack/regulatory/hosting realities (PII, payments, SLAs) when research implies them.

Set JSON field `delivery_profile` to the string: "full_software".
