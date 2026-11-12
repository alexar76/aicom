# The state of public agent skills and MCP servers, October 2026

*Muhammad Basit Ali, 13 October 2026. Dataset, method and scripts are in this repository. Data and text: CC BY 4.0. Code: MIT.*

*This is the first edition. The scan is re-run every month and each month's data is added alongside; see [Updated monthly](#updated-monthly).*

Agent skills, plugin marketplaces and MCP servers are now installed the way browser extensions once were: someone finds a repository, copies a line into a config file and the agent gains new instructions, new shell access or a new process that starts with every session. We wanted to know what that supply looks like on the ground, measured rather than guessed. So we took a random sample of 2,999 public GitHub repositories that ship a `SKILL.md`, a plugin or marketplace manifest, or an MCP `server.json`, scanned them with open-source tools, and hand-checked the scanners before trusting them.

## Key findings

- **No way to report a vulnerability:** 2,459 of 2,999 (82.0%) repositories have no `SECURITY.md`. Among the 434 with 100 or more stars it is still 75.6%.
- **MCP servers that can change under you:** 159 of 346 (46.0%) repositories that configure a local MCP server start at least one with no pinned version; 63 of 346 (18.2%) ask for the `latest` tag outright.
- **No licence:** 982 of 2,999 (32.7%) have no licence file at the root.
- **The whole shell:** 407 of 2,621 (15.5%) repositories with skills give at least one skill unscoped `Bash`, 10,073 declarations in all.
- **Skill headers that do not parse:** in 330 of 2,621 (12.6%) repositories with skills, at least one `SKILL.md` has front matter a standard YAML parser rejects; that is 4,761 of 336,285 (1.4%) files.

Every number in this list is checked against [`data/2026-10/stats.json`](data/2026-10/stats.json) in CI by [`scripts/check_numbers.py`](scripts/check_numbers.py).

## Updated monthly

This study is a monthly index. On the 1st of each month at 03:00 UTC a scheduled workflow ([`.github/workflows/monthly.yml`](.github/workflows/monthly.yml)) runs [`scripts/run_month.py`](scripts/run_month.py) end to end and opens a pull request with the results.

- **Re-measured each month:** the same 31 code search queries, a new random sample of 3,000 repositories (seed `YYYYMM01`, so November 2026 uses 20261101), the same sparse fetch of agent configuration files only, and the same scanners at the same pinned versions (skill-scan-gate 0.2.0 at e53fdc8, claude-code-tooling-skills v0.1.1, mcp-tools-lint 0.2.0 at 8540f7c). Every share in the dataset and `stats.json` is recomputed.
- **Not re-measured:** precision. The hand and automated precision checks were done once, for this first edition; later months reuse them and say "precision not re-measured" in the trend notes. Hooks are flagged automatically but not read by hand, and secret-rule findings are only counted, never triaged or named.
- **Where the data lives:** each month in `data/YYYY-MM/` (`dataset.csv`, `dataset.json`, `stats.json`, `secret_rules_aggregate.csv`). This first edition is in [`data/2026-10/`](data/2026-10/), with its precision table and chart data. `data/dataset.csv`, `data/dataset.json`, `data/stats.json` and `data/secret_rules_aggregate.csv` are always copies of the latest month, so existing links keep working. [`data/trend.csv`](data/trend.csv) has one row per month with the key findings and their denominators, drawn in `charts/trend.png`.

Each month is a new sample of what code search surfaces that month, so a change of a point or two is within sampling noise; look for movement that lasts.

![Key findings by month](charts/trend.png)

## Follow-up report: MCP tool annotations

**[Do MCP servers say which tools are safe?](docs/mcp-tool-annotations.md)** (16 October 2026) answers the question the first edition could not: whether MCP servers mark their tools with `readOnlyHint`, `destructiveHint`, `idempotentHint` and `openWorldHint`. It re-fetched the source of the 399 repositories in this sample that ship a `server.json`, at the commits in the dataset, and read the tool registrations without running anything. Of the 304 servers whose registrations could be read (17,688 tools in all), 188 (61.8%) annotate none of their tools and only 69 (22.7%) annotate every one. Of the 1,099 tools named for deleting, sending, paying or writing, 214 (19.5%) declare `destructiveHint: true`. Every share has its denominator and a 95% confidence interval; the data is in [`data/2026-10/annotations/`](data/2026-10/annotations/) and the scripts are `scripts/annotations_fetch.py` and `scripts/annotations.py`. No number in this first edition changes.

## Follow-up report: README install pins

**[Do MCP server READMEs tell you which version to run?](docs/mcp-readme-install-pins.md)** (20 October 2026) reads the launch commands in the READMEs of the same 399 repositories. Of the 264 whose READMEs contain one, 252 (95.5%) never name an exact version, and 69 (26.1%) ask for a moving tag such as `@latest`. The data is in [`data/2026-10/readme-pins/`](data/2026-10/readme-pins/).

## Follow-up report: what skills with unscoped Bash do

**[What do skills that ask for the whole shell do with it?](docs/skills-with-unscoped-bash.md)** (26 October 2026) follows up finding 4. It re-fetched 400 of the 407 repositories with a skill that grants unscoped `Bash`, at the commits in the dataset, and read up to 20 such skills in each (3,715 skills in 392 repositories) with their bundled scripts, without running anything. 1,109 of 3,715 (29.9%) show no shell command and ship no script, so the grant is unused on the page; of the 2,545 that show commands, 1,418 (55.7%) use three or fewer distinct commands and could be scoped with that many rules. 1,289 (34.7%) document or ship a riskier behaviour: installing packages (15.7%), direct HTTP calls (14.4%), recursive deletion (9.2%), `eval` (8.4%), pushing or publishing (5.0%), piping a download into a shell (2.0%), `sudo` (1.6%) or reading credentials (1.3%). Every share has its denominator and a 95% confidence interval, and the report ends with a list of what to check before installing such a skill. The data is in [`data/2026-10/skill-bash/`](data/2026-10/skill-bash/). No number in this first edition changes.

## Charts

![Share of repositories with each finding, from 82.0% with no SECURITY.md down to 3.5% with a hook that calls a non-local host](charts/chart1-prevalence.png)

| Finding | Repositories | Denominator | Share |
|---|---|---|---|
| No SECURITY.md in the repository | 2,459 | 2,999 | 82.0% |
| Stdio MCP server not pinned to a version | 159 | 346 | 46.0% |
| No licence file at the root | 982 | 2,999 | 32.7% |
| A skill allows unrestricted Bash | 407 | 2,621 | 15.5% |
| A SKILL.md has no front matter | 346 | 2,621 | 13.2% |
| A SKILL.md front matter fails YAML parsing | 330 | 2,621 | 12.6% |
| A skill description is over 1,024 characters | 146 | 2,621 | 5.6% |
| A hook calls a non-local host (hand-verified) | 13 | 373 | 3.5% |

![Findings by GitHub star band: licences improve with popularity, security policies barely move and MCP pinning does not improve](charts/chart2-by-stars.png)

| Stars | Repositories | No SECURITY.md | No licence file | Repositories with stdio MCP | Unpinned MCP |
|---|---|---|---|---|---|
| 0 | 984 | 88.2% | 53.7% | 116 | 43.1% |
| 1 to 9 | 707 | 77.9% | 33.8% | 108 | 43.5% |
| 10 to 99 | 874 | 81.5% | 16.4% | 77 | 46.8% |
| 100 or more | 434 | 75.6% | 16.6% | 45 | 57.8% |

Licences improve with popularity. Security policies barely move, and pinning does not improve at all; the 100-plus band is the worst for MCP pinning, though on only 45 repositories.

![Precision of each check, from 100% for unrestricted Bash down to 0% for two of the secret rules](charts/chart3-precision.png)

| Check | Findings checked | Correct | Precision | Used? |
|---|---|---|---|---|
| Unrestricted Bash (SSG607) | 10 | 10 | 100% | yes |
| Unpinned MCP (SSG401, 402, 403) | 22 | 19 | 86% | yes |
| Front matter fails YAML parsing | 10 | 10 | 100% | yes |
| No licence file (SSG702), against GitHub | 982 | 968 | 99% | yes |
| No security policy (SSG701), against GitHub | 2,459 | 2,420 | 98% | yes |
| Description over 1,024 characters, against parser | 513 | 470 | 92% | yes |
| Hook makes any network call | 34 | 30 | 88% | yes |
| Hook calls a non-local host | 34 | 15 | 44% | hand-verified count only |
| Linter: no "Use when" sentence | 12 | 5 | 42% | dropped |
| Linter: YAML-unsafe value, against parser | 38,442 | 4,623 | 12% | replaced by parser |
| Literal secret in MCP config (SSG405) | 11 | 6 | 55% | not used for prevalence |
| Hard-coded credential (SSG503) | 12 | 1 | 8% | not used for prevalence |
| Provider token (SSG502) | 10 | 0 | 0% | not used for prevalence |
| Private key block (SSG501) | 8 | 0 | 0% | not used for prevalence |

The chart data is in [`data/2026-10/chart-data.csv`](data/2026-10/chart-data.csv) and the full precision table in [`data/2026-10/precision.csv`](data/2026-10/precision.csv).

## What we looked at

The repositories came from GitHub code search on 13 October 2026: 93 requests across 31 queries split by file size, which surfaced 7,456 distinct non-fork repositories. We drew 3,000 at random; one failed to download, leaving 2,999. This is a sample of what search surfaces, not a census of GitHub.

The sample is young and mostly small: 2,512 of the 2,999 (84%) were created in 2026, the median repository has 4 stars, and 434 have 100 or more. 2,621 contain at least one skill, 336,285 `SKILL.md` files in all, with a median of 10 per repository. 1,047 ship a plugin manifest, 913 a marketplace manifest, 373 an agent hook configuration and 346 at least one MCP server that runs as a local process.

We fetched only the agent configuration files, ran nothing, and scanned with skill-scan-gate 0.2.0, the description linter, inventory and portability scripts from claude-code-tooling-skills, and mcp-tools-lint 0.2.0, with a standard YAML parser as a reference. [`METHOD.md`](METHOD.md) lists every query, cap, version and precision check.

## The findings in detail

**1. Most repositories give no way to report a vulnerability.** 2,459 of 2,999 (82.0%) have no `SECURITY.md` in the repository; 2,420 (80.7%) have no security policy even counting organisation-wide defaults. Among repositories with 100 or more stars the figure is still 75.6% (of 434).

**2. Nearly half of the MCP configurations run code that can change under you.** Of the 346 repositories that configure a local MCP server, 159 (46.0%) start at least one with no pinned version: 100 (28.9%) run an npm package through `npx` with no exact version, 63 (18.2%) ask for the `latest` tag outright, and 38 (11.0%) run a Python package without a version. Each session start can fetch whatever the package owner, or anyone who takes over the package, published last.

**3. A third ship with no licence.** 982 of 2,999 (32.7%) have no licence file at the root; GitHub's own licence detection finds none for 969. For zero-star repositories it is 53.7% (of 984); for repositories with 100 or more stars, 16.6% (of 434). Without a licence, a team has no clear right to copy a skill into its own repository.

**4. One in six skill repositories gives a skill the whole shell.** 407 of the 2,621 repositories with skills (15.5%) declare at least one skill whose `allowed-tools` grants `Bash` with no command scoping, 10,073 declarations in total. That is not proof of misuse, but it removes the host's chance to ask before each command.

**5. One in eight skill repositories has a skill whose header does not parse.** In 330 of 2,621 (12.6%) at least one `SKILL.md` has YAML front matter that a standard parser rejects, usually because a description contains an unquoted colon. That is 4,761 of 336,285 files (1.4%). A further 346 repositories (13.2%) contain a `SKILL.md` with no front matter at all. A host that cannot read the name and description cannot decide when to load the skill.

Two smaller results. In 146 of 2,621 skill repositories (5.6%) a description runs past 1,024 characters, a common host limit. And of the 373 repositories with hook configurations, 13 (3.5%) have a hook that, by default, calls a host other than the local machine (hand-verified); another 6 talk only to a local service. Across all 2,999, our hook check flagged 34 repositories; reading each one by hand, 30 make a network call of some kind and 15 reach a non-local host by default.

The MCP tool-schema check had little to work with, since a server has to run to list its tools and we ran nothing. In the 10 repositories that commit a tool list (986 tools), all 986 tools lack annotations and 836 declare a JSON Schema dialect that strict clients reject. Those lists are clustered and say little about MCP servers in general.

## Secrets: counted, not named

The secret-shaped-string rules fire in 471 of 2,999 repositories. Read by hand, almost all of those hits are documentation: secret-scanner regexes, placeholder tokens in setup guides, example API responses, deliberately poisoned research corpora. Reporting 471 as "repositories leaking secrets" would be wrong. We triaged every hit by structure, without displaying any value, and were left with 30 possible live credentials in 17 repositories. The totals per rule are in [`data/2026-10/secret_rules_aggregate.csv`](data/2026-10/secret_rules_aggregate.csv); the public dataset leaves out per-repository counts for the secret rules (SSG203, SSG405, SSG501, SSG502 and SSG503).

We drop the "missing when-to-use guidance" measure for a similar reason. The linter looks for the literal phrase "Use when", and in a hand check most descriptions it flagged did say when to use the skill, in other words or in another language.

## What this means for teams installing skills

- **Pin every MCP server.** Write `package@1.2.3`, never a bare name or `@latest`, and update on purpose. This is the most common finding that can run code without review, and it is a one-line fix.
- **Read `allowed-tools` before you install.** A skill that asks for unscoped `Bash` should explain why, or be scoped to the commands it needs.
- **Treat hooks as code that runs on every tool call.** Most hooks we read stay local, but some phone home on install or post session data to a webhook. Read the hook scripts, not only the manifest.
- **Check the licence before copying.** One in three repositories in this sample gives you no right to reuse the skill.
- **Lint your own skills in CI.** A colon in a description is enough to stop a host reading the skill header; it is cheap to catch and invisible until it bites.
- **Do not trust a scanner's secret count.** In this corpus most secret-shaped strings were examples. Use the findings as a reading list, then judge them.

## Limitations

- **It does not show harm.** It does not show that any repository is malicious, or that any finding was exploited. It measures the presence of patterns at one commit, on the default branch, without running anything.
- **Sample, not census.** It describes what GitHub code search surfaces, weighted towards young, small, personal projects; a curated marketplace may look better.
- **Static only.** Tool schemas of running MCP servers, hook behaviour at run time and what a skill actually does were not observed.
- **Partial fetch.** Only agent configuration paths were fetched, so a licence or `SECURITY.md` in an unusual place is missed; the GitHub cross-check bounds this at about 1 to 2%.
- **Repository-level counts** treat a mirror of thousands of skills and a single skill the same. File-level counts are given where they matter.
- **Small precision samples.** Some precision samples hold 5 to 12 findings, carry wide uncertainty and say nothing about what the scanners miss.
- **YAML strictness.** "Fails YAML parsing" means one strict parser (PyYAML 6.0.3 `safe_load`) rejects it; an agent host may be more lenient.

## Reproduce it

1. Install the tools: `pip install git+https://github.com/basitalisandhu/skill-scan-gate`, clone `basitalisandhu/claude-code-tooling-skills` and `basitalisandhu/mcp-tools-lint` (`npm ci && npm run build`), and `pip install pyyaml matplotlib`.
2. Search with `scripts/collect.py` (about 15 minutes at the code search rate limit), draw the sample with `scripts/draw_sample.py` and seed 20261013, then run `scripts/meta.py`, `scripts/fetch.py`, `scripts/scan.py` and `scripts/mcplint.py`.
3. Analyse with `scripts/build.py`, `scripts/stats.py` and `scripts/charts.py` to rebuild the dataset, the numbers in this report and the three charts.

Or run the whole pipeline for a month in one command: `GITHUB_TOKEN=... python scripts/run_month.py --month YYYY-MM` (add `--limit 30` for a quick dry run that writes to a temporary folder).

Search results change daily, so a rerun draws a different sample; the method, not the exact numbers, is what reproduces. Step-by-step commands are in [`scripts/README.md`](scripts/README.md).

To explore the data instead, [`docs/querying-the-dataset.md`](docs/querying-the-dataset.md) has worked jq and Python examples with their output, and shows how to rebuild `stats.json` and the charts offline from the committed dataset. [`docs/monthly-run.md`](docs/monthly-run.md) covers the scheduled run: the token, a dry run and the time budget.

## Repository layout

| Path | Contents |
|---|---|
| `data/YYYY-MM/` | One folder per month; `data/2026-10/` is this first edition |
| `data/YYYY-MM/dataset.csv`, `dataset.json` | One row per repository: repository name, commit, metadata and per-rule counts (secret rules withheld) |
| `data/YYYY-MM/stats.json` | Every headline number, as computed by `scripts/stats.py`; later months add a `run` block (requests, seed, tool versions) |
| `data/YYYY-MM/secret_rules_aggregate.csv` | Totals for the secret rules, with no per-repository breakdown |
| `data/2026-10/precision.csv` | Hand and automated precision checks for each rule (first edition only) |
| `data/2026-10/chart-data.csv` | The values behind the three charts |
| `data/dataset.csv`, `dataset.json`, `stats.json`, `secret_rules_aggregate.csv` | Copies of the latest month; `data/precision.csv` and `data/chart-data.csv` stay the first edition's |
| `data/trend.csv` | One row per month: key findings, denominators, seed, request counts and notes |
| `charts/` | The three first-edition charts and `trend.png` |
| `scripts/` | Collection, fetch, scan and analysis scripts, `run_month.py` and `plot_trend.py` for the monthly run, and `check_numbers.py` |
| `docs/` | The follow-up reports on MCP tool annotations, on README install pins and on what skills with unscoped Bash do, worked examples of querying the dataset, and how the monthly run works |
| `data/2026-10/annotations/` | The tool annotation report's data: `results.json` (every number, with intervals), `tools.csv` (one row per tool), `repos.csv` (one row per selected repository, with the fetched commit) and `hand-check.csv` |
| `data/2026-10/readme-pins/` | The README install pins report's data: `results.json` (every number, with intervals), `commands.csv` (one row per launch command), `repos.csv` (one row per selected repository, with the fetched commit) and `hand-check.csv` |
| `data/2026-10/skill-bash/` | The unscoped Bash report's data: `results.json` (every number, with intervals), `skills.csv` (one row per skill: grant, commands, heads, scripts and the first line each rule matched), `repos.csv` (one row per selected repository, with the fetched commit) and `hand-check.csv` |
| `tests/` | Tests for `run_month.py`, the tool annotation scripts, the README install pin scripts and the unscoped Bash scripts, with fixtures |
| `METHOD.md` | Full method |

## Responsible disclosure

The structural triage left 30 possible live credentials in 17 repositories. Before publication each owner was re-checked: 4 repositories turned out to hold documented test values or shortened examples. None of the remaining 13 had GitHub private vulnerability reporting enabled; 2 owners were contacted by email and 11 received a short public notice that names no file, line or key type and asks them to rotate the key. No repository with a possible live credential is named here, and the public dataset leaves out per-repository counts for the secret rules.

## How to cite

Cite the repository with the metadata in [`CITATION.cff`](CITATION.cff) (GitHub shows a "Cite this repository" button), or:

> Ali, M. B. (2026). *The state of public agent skills and MCP servers, October 2026* (Version 1.0.0) [Data set and report]. https://github.com/basitalisandhu/agent-skills-state-2026

For the follow-up reports:

> Ali, M. B. (2026). *Do MCP servers say which tools are safe? Tool annotations in 304 public servers, October 2026* (Version 1.1.0) [Data set and report]. https://github.com/basitalisandhu/agent-skills-state-2026/blob/main/docs/mcp-tool-annotations.md

> Ali, M. B. (2026). *Do MCP server READMEs tell you which version to run? Install pins in 264 public servers, October 2026* (Version 1.2.0) [Data set and report]. https://github.com/basitalisandhu/agent-skills-state-2026/blob/main/docs/mcp-readme-install-pins.md

> Ali, M. B. (2026). *What do skills that ask for the whole shell do with it? Unscoped Bash in 3,715 public skills, October 2026* (Version 1.3.0) [Data set and report]. https://github.com/basitalisandhu/agent-skills-state-2026/blob/main/docs/skills-with-unscoped-bash.md

## Related datasets

- [RugSnare drift-watch corpus](https://github.com/Paraphern/rugsnare/blob/main/tools/drift-watch-corpus.json) (Paraphern, Apache-2.0): a public, machine-readable record of how the tool contracts of 28 npm-distributed MCP servers and two skills collections changed across released versions, with a [page per server](https://github.com/Paraphern/rugsnare/tree/main/docs/servers) giving the version window and a repro command. It measures what a pinned version later serves, which this study does not.

## Related tools

- [skill-scan-gate](https://github.com/basitalisandhu/skill-scan-gate): CI gate for skills and plugins (the scanner used here).
- [claude-code-tooling-skills](https://github.com/basitalisandhu/claude-code-tooling-skills): skills to review a third-party skill before installing it and to lint your own descriptions.
- [mcp-tools-lint](https://github.com/basitalisandhu/mcp-tools-lint): lint MCP tool schemas and annotations.
- [agent-off-switch](https://github.com/basitalisandhu/agent-off-switch): find every AI agent identity in Microsoft 365, AWS and GitHub and switch it off.
- [ai-agent-incidents](https://github.com/basitalisandhu/ai-agent-incidents): open dataset of AI agent security incidents.
- Docs hub with every tool and post: https://basitalisandhu.github.io/

## Licence

Data and text (the `data/` and `charts/` folders, this README and `METHOD.md`) are licensed under [CC BY 4.0](LICENSE-DATA). Code (the `scripts/` and `tests/` folders and the workflows) is licensed under the [MIT licence](LICENSE).
