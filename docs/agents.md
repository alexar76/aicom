# Pipeline Agents

The pipeline roster contains the following first-class agents:

- `analyst` — market / discovery analysis
- `pm` — product specification
- `methodologist` — domain process compliance after spec and after implementation
- `architect` — architecture and UX direction
- `design_critic` — optional art-direction gate
- `developer` / `dev` — product implementation
- `hardening` — optional stabilization pass
- `qa` — quality gates, tests, runtime probes
- `security` — security review
- `devops` — packaging / deploy readiness
- `marketing` — marketplace content
- `sales` — pricing / sales readiness
- `evolution_analyst` — post-launch evolution analysis

UI pseudo-stage:

- `designer` — UI direction exposed in the Admin pipeline, backed by Architect artifacts rather than a separate worker agent.

## System prompts (markdown)

Agent **system role prompts** live under **`agents/prompts/*.md`** and are loaded at import time via **`agents/prompts/load_prompt.py`** (same pattern as Architect). This keeps prompts reviewable in PRs without scrolling Python modules.

| File | Agent / use |
|------|-------------|
| `architect_role_prompt.md` | Architect |
| `pm_system_prompt_base.md`, `pm_section_*.md`, `pm_output_*.md` | PM (assembled by profile) |
| `developer_core_prompt.md` | Developer |
| `qa_system_prompt.md` | QA |
| `security_system_prompt.md` | Security |
| `devops_system_prompt.md` | DevOps |
| `marketing_system_prompt.md` | Marketing |
| `sales_system_prompt.md` | Sales |
| `analyst_research_prompt.md`, `analyst_monitor_prompt.md` | Analyst |
| `methodologist_system_prompt.md` | Methodologist |
| `design_critic_system_prompt.md` | Design critic |
| `evolution_analyst_system_prompt.md` | Evolution analyst |

Regenerate from Python constants (if needed): `python3 scripts/export_agent_prompts.py`.

**Import rule:** `load_prompt` and `logging` must live in **executable Python** (after the module docstring), not inside the docstring text — otherwise the pipeline worker fails agent init and runs **fallback-only** tasks.

See also:

- `pipeline-operations.md`
- `methodology-agent.md`
- `factory-capabilities.md`
