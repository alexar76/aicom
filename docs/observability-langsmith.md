# Observability: LangSmith (and any OTel backend)

AI-Factory emits OpenTelemetry traces from every LLM call and pipeline stage.
Because traces use the standard `gen_ai.*` semantic conventions, **any**
OTel-compatible backend renders them as proper LLM calls (model / prompt /
completion / tokens / cost) — not as opaque spans.

This document focuses on **LangSmith** because that is the most common ask,
but the same setup works for **Phoenix** (Arize), **Helicone**, **Jaeger**,
**Tempo**, **Datadog**, and others. Only the `OTEL_EXPORTER_OTLP_*` env vars
change.

The integration is **opt-in**: with no env vars set, tracing is a no-op and
costs you nothing.

---

## 1. What you'll see

The trace tree mirrors how the factory actually runs work:

```
factory.pipeline_stage:developer        ← parent (pipeline stage)
├── llm.generate                        ← child (LLM call via the router)
│   gen_ai.system          = anthropic
│   gen_ai.request.model   = claude-3-5-sonnet
│   gen_ai.usage.input_tokens  = 1240
│   gen_ai.usage.output_tokens = 380
│   gen_ai.usage.total_tokens  = 1620
├── llm.generate
└── llm.generate
```

For paid AI-Market invocations the trace also carries the UNI receipt id, so a
single trace answers: "what work was done, with what model, at what cost in
tokens — and which UNI receipt paid for it?"

**Where the attributes come from in the code:**

| Span | File | Attributes |
| ---- | ---- | ---------- |
| `factory.pipeline_stage:<agent>` | [`pipeline_worker.py`](../pipeline_worker.py) `_process_task` | `factory.task_id`, `factory.agent_type`, `factory.target_state`, `factory.retry`, `aifactory.product_id` |
| `llm.generate` | [`llm/router.py`](../llm/router.py) `generate` | `gen_ai.system`, `gen_ai.operation.name=chat`, `gen_ai.request.model`, `gen_ai.request.temperature`, `gen_ai.request.max_tokens`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.total_tokens`, `gen_ai.response.model`, plus legacy `llm.provider` / `llm.task_type` / `aifactory.product_id` |

> **Token counts** use the OTel-recommended `chars/4` heuristic fallback, since
> the in-tree LLM router currently returns plain strings without provider
> usage metadata. The number is good enough for cost trends but not for
> finance-grade billing. When you wire per-provider usage payloads, replace
> the heuristic in `llm/router.py` and the same span will start showing real
> figures everywhere downstream.

---

## 2. Five-minute LangSmith setup

### 2.1. Get an API key
Sign in at <https://smith.langchain.com>, open your workspace settings, copy
the API key, and create (or note) the project you want traces in (e.g.
`aifactory`).

### 2.2. Set env vars

Add to `.env` (or your secrets manager — these go straight to the process
environment):

```sh
OTEL_SERVICE_NAME=aicom-web
OTEL_EXPORTER_OTLP_ENDPOINT=https://api.smith.langchain.com/otel
OTEL_EXPORTER_OTLP_HEADERS=x-api-key=<your-langsmith-api-key>,Langsmith-Project=aifactory
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=1.0
```

Notes:

* `OTEL_EXPORTER_OTLP_HEADERS` is a comma-separated `k=v` list. The
  `x-api-key` header is what authenticates against LangSmith; the
  `Langsmith-Project` header routes spans into the named project.
* Sampler `1.0` = 100% of traces. For high-volume prod, drop to `0.05`
  (5%) to stay inside the LangSmith free tier.
* `OTEL_SERVICE_NAME` shows up as the service in LangSmith. The pipeline
  worker uses `aicom-worker` by default so you can split web vs. worker
  traffic. Override with `OTEL_SERVICE_NAME=` if you want a single bucket.

### 2.3. Restart the app

```sh
docker compose restart app pipeline-worker
# or, locally:
./run.sh
```

On startup you should see:

```
INFO core.tracing: OpenTelemetry tracing enabled (service=aicom-web)
INFO __main__: OpenTelemetry tracing active (web backend)
```

Trigger any LLM-backed flow (e.g. open the storefront, run a pipeline tick,
invoke an AI-Market capability) — within ~30 s the trace appears in the
LangSmith project view.

### 2.4. (Optional) wire receipt → trace links

If you set `OTEL_TRACE_URL_TEMPLATE`, `GET /api/uni/receipt/{id}` will return
a clickable `trace_url` pointing at the underlying LLM trace:

```sh
OTEL_TRACE_URL_TEMPLATE=https://smith.langchain.com/o/<org>/projects/p/<project>/r/{trace_id}
```

Replace `<org>` and `<project>` with the values from your LangSmith URL bar
(visible when you open any trace). The placeholder `{trace_id}` is the only
substitution made.

Example response:

```json
{
  "id": "rcpt_a1b2c3d4e5f60718",
  "kind": "invoke",
  "amount_uni": "42",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "trace_url": "https://smith.langchain.com/o/.../projects/p/.../r/4bf92f3577b34da6a3ce929d0e0e4736"
}
```

The `trace_id` itself is **inside the signed receipt payload** (column
`uni_receipts.trace_id`), so the link is tamper-evident: a receipt holder
can independently verify that the trace they're looking at is the one
that backed their payment.

---

## 3. Other backends — same code, different env

### Phoenix (local, self-hosted)
```sh
OTEL_SERVICE_NAME=aicom-web
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:6006/v1/traces
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=1.0
```

### Helicone
```sh
OTEL_SERVICE_NAME=aicom-web
OTEL_EXPORTER_OTLP_ENDPOINT=https://api.helicone.ai/v1/trace/log
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer <helicone-api-key>
```

### Jaeger / Tempo / Datadog Agent
Standard OTLP HTTP endpoint, no auth header:
```sh
OTEL_SERVICE_NAME=aicom-web
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

---

## 4. Privacy / cost notes

* **Prompt and completion text are NOT yet attached to spans.** Only
  metadata (model, token counts, task type, product id). If you want to
  capture content for LangSmith side-by-side comparisons or evals, add a
  span event in `llm/router.py` — but think about PII first if your
  invokes carry customer data.
* **Tokens are estimates** (chars/4). For finance-grade attribution, pipe
  real usage from the provider response into the existing `gen_ai.usage.*`
  attributes. The wiring point is `llm/router.py`, immediately after
  `await self._generate_via_provider(...)`.
* **Sampling.** Default `OTEL_TRACES_SAMPLER_ARG=1.0` traces everything.
  In production with thousands of invokes/day, drop to `0.05` — 5% of
  traces × LangSmith per-trace cost is the usual sweet spot. The receipt
  `trace_id` will still be populated for the spans that *do* get sampled;
  for the rest it will be empty, which the API surfaces cleanly.
* **No vendor lock-in.** All instrumentation lives behind the standard
  OTel SDK and `gen_ai.*` semantic conventions. Swapping LangSmith for
  Phoenix or Helicone is one env change, no code edits.

---

## 5. Troubleshooting

| Symptom | Likely cause | Fix |
| ------- | ------------ | --- |
| Startup log doesn't say "OpenTelemetry tracing enabled" | `OTEL_EXPORTER_OTLP_ENDPOINT` not set, or the OTel SDK packages aren't installed | Check `pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http`; verify env var is in the actual process environment (not just `.env.example`) |
| LangSmith shows opaque `llm.generate` spans without model/tokens | `gen_ai.system` attribute missing, e.g. an older deploy hit a different LLM code path | Confirm the LLM call goes through `llm/router.py:generate`; check the router log line `Routing to provider '...'`. Custom LLM call sites need to be wrapped in `core.tracing.span(...)` to participate |
| Traces appear but no `factory.pipeline_stage` parent | A pipeline task was executed outside `_process_task` (e.g. ad-hoc script) | Wrap the call site in `core.tracing.span("factory.pipeline_stage:adhoc", attributes={...})` |
| `trace_url` empty on receipts | `OTEL_TRACE_URL_TEMPLATE` not set, or the receipt was issued before tracing was enabled | Set the env var; new receipts get the URL, old ones stay empty (immutable signed payload) |
| Wrong project name in LangSmith | `Langsmith-Project` header missing from `OTEL_EXPORTER_OTLP_HEADERS` | Add `Langsmith-Project=<name>` to the comma-separated header list |
| High LangSmith bill | Sampler at 100% in production | Lower `OTEL_TRACES_SAMPLER_ARG` to `0.05`–`0.1` |

---

## 6. Roadmap

These extensions are intentionally **out of scope** for this iteration:

* **Per-provider real token counts** (replace chars/4). One-line change per
  provider in `llm/router.py` once the provider response payload is plumbed
  through.
* **Prompt / completion capture as span events.** Gated behind a per-tenant
  opt-in flag to keep PII out of LangSmith by default.
* **Auto-instrumentation for FastAPI / SQLAlchemy / httpx** via
  `opentelemetry-instrumentation-*` packages. Drop-in.
* **Receipt → trace bidirectional link.** Today the receipt links to the
  trace; the reverse (trace → receipt) requires posting the receipt id as
  a custom attribute on the root span (`uni.receipt_id`), one line in
  `core/uni/receipts.py`.
