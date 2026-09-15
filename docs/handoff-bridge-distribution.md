# Handoff — getting the bridges in front of framework users

**Task owner:** whoever picks this up · **Written:** 2026-08-23 · **State verified the same day**

The goal is not "submit to catalogues". It is: **a developer who already uses LangGraph, CrewAI,
AutoGen or an MCP client discovers AIMarket without ever visiting our site, and installs it in one
command.** Everything below serves that sentence; if a step does not, drop it.

Read §1 before planning anything. Two of the four targets do not work the way we assumed.

---

## 1. What is already true (checked 2026-08-23)

| Thing | State |
|---|---|
| `aimarket-bridges` on PyPI | **0.1.0, live.** LangChain/LangGraph, CrewAI, AutoGen adapters in one package with per-framework extras |
| Public repo | [alexar76/aimarket-bridges](https://github.com/alexar76/aimarket-bridges) — exists, 0 stars, topics `agent-economy, agents, aimarket, autogen, crewai, langchain, langgraph, mcp, python, tools` |
| Framework floors | langchain-core 1.x · langgraph 1.x · crewai 1.x · autogen-core/autogen-agentchat 0.7.x (verified 2026-07-29) |
| Official MCP registry | **Done.** Five servers active: `aimarket-hub` (remote `https://modelmarket.dev/mcp`), `aimarket-mcp` (0.3.0), `aimarket-oracle-gateway`, `aimarket-plugins`, `argus3` |
| Glama | Indexed; `aimarket-mcp`'s PyPI homepage already points at its Glama page |
| PyPI siblings | `aimarket-agent` 2.2.0, `aimarket-mcp` 0.3.0, npm `@aimarket/agent` 0.2.1 |

So the MCP side is mostly finished. The work that remains is the three agent frameworks — and there
the picture is not what a generic "open a PR to their integrations directory" plan assumes.

---

## 2. LangChain — they no longer accept integration PRs

**Verify this first, then act.** The LangChain contributing guide states plainly:

> Anyone can build and publish their own LangChain integration package. New integrations are not
> accepted as PRs to `langchain-ai` repos — they must be published independently to PyPI or npm.

`langchain-community` is sunset. There is no directory to be merged into. Do **not** spend a day
writing a PR that will be closed.

What actually produces discovery, in order of value:

1. **Ship a `langchain-aimarket` distribution on PyPI.** The ecosystem convention is
   `langchain-<provider>`, and that name is what people search and what LLMs suggest. Keep the code
   in `aimarket-bridges`; publish a thin package that depends on it and re-exports
   `aimarket_bridges.langchain` as `langchain_aimarket`. Ten lines plus metadata. Check the name is
   free on PyPI before promising it.
2. **Pass the standard integration tests.** LangChain publishes `langchain-tests` for exactly this;
   a tool integration that passes them behaves the way LangGraph users expect (sync + async,
   schema round-trip, error surface). Run them in CI and say so in the README — it is the single
   most credible signal on an integration page.
3. **Write the page they will actually land on.** One `README` section titled for the search a
   person performs ("LangGraph tools that get paid per call"), with a runnable 10-line snippet and
   the output of a real invoke including the signed receipt.
4. **Ask for a link where links are given out.** The LangChain forum and Discord accept
   show-and-tell posts; awesome-lists (`awesome-langchain`) still take PRs. These are small, but
   they are the only inbound links that exist now that the docs are closed.

**Definition of done:** `pip install langchain-aimarket` works, `langchain-tests` green in CI, and a
search for "langgraph paid tools" surfaces something of ours on the first page.

---

## 3. CrewAI — one PR, but ask before writing it

The `crewAIInc/crewAI-tools` repository is **deprecated**; tools now live inside the monorepo at
[`crewAIInc/crewAI` → `lib/crewai-tools/`](https://github.com/crewAIInc/crewAI/tree/main/lib/crewai-tools).
Their `.github/CONTRIBUTING.md` describes the normal fork → branch → PR workflow and where tools
live, but it does **not** state a policy on third-party tools. That is the open question.

Steps, in this order:

1. **Open a GitHub Discussion or issue first** in `crewAIInc/crewAI`: "Would you accept an
   `AIMarketTools` tool in `lib/crewai-tools`, or do you prefer external packages listed in docs?"
   One paragraph, link to the PyPI package and to a 20-second demo. Wait for an answer before
   writing code. If they say no, the fallback is §2's playbook applied to CrewAI: keep the external
   package and get it into their docs' integrations list.
2. **If yes**, the tool has to look like theirs: a `BaseTool` subclass, an explicit Pydantic
   `args_schema`, a real docstring (CrewAI feeds it to the model as the description), full type
   annotations, and tests next to the existing tool tests.
3. **Keep the network out of the test path.** Their CI has no access to our hub; the test must run
   against a fixture, with the live call behind an opt-in marker.
4. **Docs page in the same PR** if their tools index is docs-driven.

**Definition of done:** either a merged PR, or a written answer from a maintainer that external
packages are the accepted path — both are useful; an unanswered PR is not.

---

## 4. AutoGen — no PR at all, it is a GitHub topic (and the framework question is answered)

AutoGen's "Discover community projects" page is generated from GitHub topic searches. Their
guidance: tag the repository with **`autogen-extension`** (or `autogen-sample`, or `autogen`), and
prefix the package name with `autogen-` so it is findable.

Our repo carries `autogen` but **not `autogen-extension`** — that one topic is the whole listing
mechanism. It needs a token with write access to `alexar76/*`:

```bash
echo '{"names":["agent-economy","agents","aimarket","autogen","autogen-extension","crewai",
"langchain","langgraph","mcp","python","tools"]}' \
  | gh api -X PUT repos/alexar76/aimarket-bridges/topics --input -
```

### Which AutoGen — measured 2026-08-23, not a guess

| Project | Stars | Commits, last 30 days | Last push | PyPI downloads / month |
|---|---:|---:|---|---:|
| `microsoft/autogen` (v0.4, what our adapter targets) | 60,594 | **0** | 2026-04-15 | `autogen-agentchat` 1,078,361 · `autogen-core` 999,389 |
| `microsoft/agent-framework` (GA 1.0, April 2026) | 13,062 | **100+** | 2026-08-23 | `agent-framework` 1,633,943 · `agent-framework-core` 2,549,799 |
| `ag2ai/ag2` (community fork of the 0.2 line) | 4,883 | 69 | 2026-08-23 | `ag2` 405,647 · `pyautogen` 475,072 |

Read the middle column first: **AutoGen has not received a commit in four months.** The star count is
a monument, not an audience. Downloads on a frozen framework are largely CI and mirrors, and they
decay; Agent Framework is already ahead on that number anyway, while being four months old.

**Decision, so nobody re-litigates it:**

1. **Keep the AutoGen adapter as is.** It is written, it is tested, and a frozen framework cannot
   break it. Maintenance cost is now approximately zero, so removing it would only lose reach.
2. **Do not invest in AG2.** Smallest audience of the three, and it continues the 0.2 line our
   adapter does not target — that is a rewrite, not a port. Add it only if a user asks for it.
3. **The next adapter to write is Microsoft Agent Framework**, not another AutoGen variant. In
   Agent Framework a tool is a plain function wrapped with `@ai_function` / `@tool`, whose Pydantic
   model is derived from the signature — which is exactly what `aimarket_bridges.schema`
   (`model_from_schema`) already produces from a capability's JSON Schema. `catalog.py`,
   `client.py`, `receipts.py` and `schema.py` are framework-agnostic and get reused unchanged, so
   this is roughly one day including tests, the same size as the three existing adapters
   (~450–530 lines each, most of it glue).
4. **Set the topic anyway** while doing it — it costs two minutes and the AutoGen ecosystem page is
   still where people from the v0.4 generation look.

**Definition of done:** topic set; `aimarket_bridges/agent_framework.py` with tests, an extra
(`pip install "aimarket-bridges[agent-framework]"`), and a README section beside the other three.

## 5. MCP clients — the registry is done, the clients are not

Nothing to do in the official registry beyond keeping it fresh: each release must republish
`server.json`, or the registry advertises a version nobody can install.

```bash
mcp-publisher login github
mcp-publisher publish --dry-run   # validate first
mcp-publisher publish
```

What is actually left:

- **Smithery** — needs an MCPB bundle and an interactive login; it was left pending in the July
  campaign. Finish it or write down why it was abandoned.
- **mcp.so** — a submission was made in July; confirm whether the listing went live.
- **Client-side directories** — Cursor, VS Code and Claude's connector directory each curate their
  own list and do not read the official registry. One application each, and each wants a working
  remote endpoint plus a privacy/security note. `https://modelmarket.dev/mcp` is live and is the
  strongest asset we have here, because it needs no install at all.
- **Version drift** — `aimarket-mcp` is 0.3.0 on PyPI and 0.3.0 in the registry today. Add the
  republish to the release checklist so they cannot diverge.

**Definition of done:** every directory we are in lists a version that installs, and each directory
we are not in has either an application filed or a line saying why not.

---

## 6. Prerequisites that apply to all four

Do these before any submission — several catalogues reject on exactly these:

- **Repo hygiene.** `aimarket-bridges` currently ships `.coverage` and `coverage.json` in the public
  tree. Remove them and add them to `.gitignore`.
- **A quickstart that fits on one screen**, at the very top of the README, with real output.
- **A runnable example per framework** in `examples/`, each under 30 lines.
- **`LICENSE`, `SECURITY.md`, `CODE_OF_CONDUCT.md`** — present already; keep them.
- **CI badge that is true.** Reviewers click it.

## 7. Suggested order

| Order | Task | Effort | Why first |
|--:|---|---|---|
| 1 | AutoGen topic + repo hygiene | 30 min | Free listing, unblocks everything else |
| 2 | CrewAI question to maintainers | 30 min | Answer takes days to arrive — start the clock |
| 3 | `langchain-aimarket` shim + `langchain-tests` in CI | 1 day | The largest audience, and fully in our control |
| 4 | MCP client directories | 1 day | Highest quality traffic; the remote endpoint sells itself |
| 5 | CrewAI PR or docs listing | 1 day | Depends on the answer from step 2 |
| 6 | Microsoft Agent Framework adapter | 1 day | The only framework in §4 that is both growing and unserved |

## 8. Report back with

Not "submitted to X". For each target: the URL of what is now public, the version it advertises, and
one sentence on whether it can actually be installed from there. If a target turned out to be closed
or worthless, say so and reclaim the time — that is a result too, and §2 is the proof that the
assumption behind this whole ticket was wrong for one of the four.
