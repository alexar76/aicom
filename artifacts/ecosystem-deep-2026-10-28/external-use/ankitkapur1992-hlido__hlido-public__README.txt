# Hlido — the trust layer for AI agents

Independent, evidence-backed reviews of AI agents. C2PA-signed proof, machine-readable scorecards, and a Laddoo Score that's consistent across every reviewed agent — so buyers, teams, and other agents can tell which ones live up to their pitch.

This repository is the **public mirror** of [hlido.eu](https://hlido.eu). Every review pushed live on the canonical site is mirrored here automatically — sanitized, machine-readable, fork-friendly. Use it from your own scripts, agents, or analysis pipelines without scraping HTML.

---

## Why Hlido exists

Every week, dozens of new AI agents launch. Each one claims to write code, run workflows, handle support, or close deals. Some deliver. Most don't — at least not the way their landing page implies.

Until now, the only way to know was to sign up, burn a weekend, and find out yourself. That doesn't scale — not for procurement teams choosing vendors, not for builders wiring agents into production, and crucially not for **other agents** that will increasingly make those calls on our behalf.

Hlido is the independent party that actually tests every claim. We publish verdicts grounded in captured evidence, track them over time, and surface the patterns the market needs to see.

## What we provide

- **Independent reviews of AI agents** — public-surface tested for web tools, live CLI tested for terminal tools, claim-by-claim verification for everything
- **A consistent score** — every agent gets a Laddoo Score (0–100) derived from a fixed evaluation framework. Tier mapping: `VITAL` ≥ 90 · `STEADY` ≥ 70 · `FADING` ≥ 40 · `FLATLINE` < 40
- **C2PA-signed evidence** — screenshots and (where applicable) terminal casts are cryptographically signed, so the captured proof can be verified as un-tampered
- **A live MCP server** — 9 tools exposed at [`https://hlido.eu/mcp`](https://hlido.eu/mcp) for human and agent consumers. JSON-RPC 2.0, no auth required, free to call. Tools include `trust_check`, `find_similar_agents` (semantic search), `get_scorecard` (full claim table), `request_quick_audit`, `verify_claim`, `compare_agents`, and more
- **Structured machine-readable scorecards** — every review is also published as a JSON file in this repo (`scorecards/{slug}.json`) with the full claim-vs-evidence table, source-surface citations, and stable schema (`schema_version: 1.0`)
- **An independent MCP-server safety register** — MCP servers scored safety-first (tool-poisoning / dangerous-capability / auth-posture red-flags → `SAFE` / `CAUTION` / `RISKY` / `DANGEROUS`) with published per-flag evidence, never a bare number. Early first cohort: [hlido.eu/mcp/](https://hlido.eu/mcp/) · data at [`/data/mcp-register.json`](https://hlido.eu/data/mcp-register.json)
- **Distribution everywhere** — also indexed on [Smithery](https://smithery.ai/servers/ankitkapur1992/hlido), [HuggingFace dataset](https://huggingface.co/datasets/hlido-eu/agent-benchmark), and the [community awesome-mcp-servers list](https://github.com/punkpeye/awesome-mcp-servers)

## Reviewed agents (1044)

| Slug | Name | Category | Laddoo | Tier |
|---|---|---|---|---|
| [`klariqo`](https://hlido.eu/reviews/klariqo/) | Klariqo | Voice | 58 | FADING |
| [`baton`](https://hlido.eu/reviews/baton/) | Baton | Frameworks & Eval | 64 | FADING |
| [`openowl`](https://hlido.eu/reviews/openowl/) | OpenOwl | Workflow & Automation | 50 | FADING |
| [`naoma-ai-demo-agent`](https://hlido.eu/reviews/naoma-ai-demo-agent/) | Naoma AI Demo Agent | Customer Experience | 80 | — |
| [`holo`](https://hlido.eu/reviews/holo/) | Holo | Marketing & Content | 50 | FADING |
| [`parahelp`](https://hlido.eu/reviews/parahelp/) | Parahelp | Customer Experience | 75 | — |
| [`parakeeet-ai`](https://hlido.eu/reviews/parakeeet-ai/) | Parakeeet AI | Sales | 75 | STEADY |
| [`workbeaver`](https://hlido.eu/reviews/workbeaver/) | WorkBeaver | Productivity | 63.4 | — |
| [`gumloop`](https://hlido.eu/reviews/gumloop/) | Gumloop | Workflow & Automation | 78 | — |
| [`aider`](https://hlido.eu/reviews/aider/) | Aider | Coding | 92 | — |
| [`jared-so`](https://hlido.eu/reviews/jared-so/) | jared-so | Productivity | 40 | — |
| [`raccoon-ai`](https://hlido.eu/reviews/raccoon-ai/) | raccoon-ai | Productivity | 70 | — |
| [`needle-2-0`](https://hlido.eu/reviews/needle-2-0/) | needle-2-0 | Productivity | 80 | — |
| [`zooclaw`](https://hlido.eu/reviews/zooclaw/) | zooclaw | Productivity | 40 | — |
| [`agentpulse-by-rectify`](https://hlido.eu/reviews/agentpulse-by-rectify/) | agentpulse-by-rectify | Workflow & Automation | 40 | — |
| [`genspark`](https://hlido.eu/reviews/genspark/) | genspark | Research | 40 | — |
| [`askiva`](https://hlido.eu/reviews/askiva/) | askiva | Research | 40 | — |
| [`influcio`](https://hlido.eu/reviews/influcio/) | influcio | AI Agent | 65 | — |
| [`ovren`](https://hlido.eu/reviews/ovren/) | ovren | AI Agent | 40 | — |
| [`panorama`](https://hlido.eu/reviews/panorama/) | panorama | AI Agent | 40 | — |
| [`poke`](https://hlido.eu/reviews/poke/) | poke | AI Agent | 60 | — |
| [`spine-ai`](https://hlido.eu/reviews/spine-ai/) | spine-ai | AI Agent | 65 | — |
| [`synthflow-ai`](https://hlido.eu/reviews/synthflow-ai/) | synthflow-ai | AI Agent | 80 | — |
| [`flux`](https://hlido.eu/reviews/flux/) | flux | AI Agent | 40 | — |
| [`agentmail`](https://hlido.eu/reviews/agentmail/) | agentmail | AI Agent | 53 | — |
| [`lmarena`](https://hlido.eu/reviews/lmarena/) | Chatbot Arena (LMArena) | Frameworks & Eval | 40 | — |
| [`perplexity`](https://hlido.eu/reviews/perplexity/) | Perplexity | Research | 53 | — |
| [`happycapy`](https://hlido.eu/reviews/happycapy/) | happycapy | AI Agent | 90 | — |
| [`back4app-ai-agent`](https://hlido.eu/reviews/back4app-ai-agent/) | Back4app AI Agent | AI Agent | 40 | — |
| [`luma-ai-agents`](https://hlido.eu/reviews/luma-ai-agents/) | Luma AI Agents | AI Agent | 65 | — |
| [`agent-ai`](https://hlido.eu/reviews/agent-ai/) | Agent.ai | AI Agent | 78 | — |
| [`windsurf`](https://hlido.eu/reviews/windsurf/) | Windsurf | Coding | 65 | — |
| [`usercall`](https://hlido.eu/reviews/usercall/) | UserCall | AI Agent | 40 | — |
| [`mindstudio`](https://hlido.eu/reviews/mindstudio/) | MindStudio | AI Agent | 78 | — |
| [`foyer`](https://hlido.eu/reviews/foyer/) | Foyer | AI Agent | 40 | — |
| [`hubspot-breeze`](https://hlido.eu/reviews/hubspot-breeze/) | HubSpot Breeze | AI Agent | 53 | — |
| [`octoclaw`](https://hlido.eu/reviews/octoclaw/) | OctoClaw | AI Agent | 40 | — |
| [`molmoweb`](https://hlido.eu/reviews/molmoweb/) | MolmoWeb | AI Agent | 40 | — |
| [`guide-ai`](https://hlido.eu/reviews/guide-ai/) | Guide | AI Agent | 53 | — |
| [`adobe-firefly`](https://hlido.eu/reviews/adobe-firefly/) | Adobe Firefly | AI Agent | 82 | — |
| [`tad-ai`](https://hlido.eu/reviews/tad-ai/) | Tad AI | AI Agent | 65 | — |
| [`genfuse-ai`](https://hlido.eu/reviews/genfuse-ai/) | GenFuse AI | AI Agent | 78 | — |
| [`outset-ai`](https://hlido.eu/reviews/outset-ai/) | Outset AI | AI Agent | 65 | — |
| [`autonoly`](https://hlido.eu/reviews/autonoly/) | Autonoly | AI Agent | 78 | — |
| [`cockpit-ai`](https://hlido.eu/reviews/cockpit-ai/) | Cockpit AI | AI Agent | 53 | — |
| [`lessie-ai`](https://hlido.eu/reviews/lessie-ai/) | Lessie AI | AI Agent | 78 | — |
| [`aiagent-app`](https://hlido.eu/reviews/aiagent-app/) | AiAgent.app | AI Agent | 65 | — |
| [`klipy`](https://hlido.eu/reviews/klipy/) | Klipy | AI Agent | 40 | — |
| [`fuseai`](https://hlido.eu/reviews/fuseai/) | FuseAI | AI Agent | 53 | — |
| [`relay-app`](https://hlido.eu/reviews/relay-app/) | Relay.app | AI Agent | 78 | — |
| [`canary-ai`](https://hlido.eu/reviews/canary-ai/) | Canary | AI Agent | 53 | — |
| [`augment-code`](https://hlido.eu/reviews/augment-code/) | Augment Code (Intent) | Coding | 78 | — |
| [`cursor`](https://hlido.eu/reviews/cursor/) | Cursor | Coding | 78 | — |
| [`cto-new`](https://hlido.eu/reviews/cto-new/) | cto.new | AI Agent | 90 | — |
| [`orange-slice`](https://hlido.eu/reviews/orange-slice/) | Orange Slice | AI Agent | 90 | — |
| [`claimcheck`](https://hlido.eu/reviews/claimcheck/) | ClaimCheck | Coding | 65 | — |
| [`kaily`](https://hlido.eu/reviews/kaily/) | Kaily | AI Agent | 78 | — |
| [`magine`](https://hlido.eu/reviews/magine/) | Magine | AI Agent | 65 | — |
| [`blink-ai`](https://hlido.eu/reviews/blink-ai/) | Blink | AI Agent | 65 | — |
| [`cosyra-2`](https://hlido.eu/reviews/cosyra-2/) | Cosyra | AI Agent | 78 | — |
| [`catdoes-v4`](https://hlido.eu/reviews/catdoes-v4/) | CatDoes v4 | AI Agent | 65 | — |
| [`denovo`](https://hlido.eu/reviews/denovo/) | Denovo | AI Agent | 78 | — |
| [`athena-intel`](https://hlido.eu/reviews/athena-intel/) | Athena Intelligence | Workflow & Automation | 53 | — |
| [`anthropic-computer-use`](https://hlido.eu/reviews/anthropic-computer-use/) | Anthropic Computer Use | Infrastructure | 82 | — |
| [`anyword`](https://hlido.eu/reviews/anyword/) | Anyword | Marketing & Content | 70 | — |
| [`axe`](https://hlido.eu/reviews/axe/) | Axe | AI Agent | 40 | — |
| [`braintrust`](https://hlido.eu/reviews/braintrust/) | Braintrust | Frameworks & Eval | 90 | — |
| [`cerebras`](https://hlido.eu/reviews/cerebras/) | Cerebras | Infrastructure | 65 | — |
| [`cassidy-ai`](https://hlido.eu/reviews/cassidy-ai/) | Cassidy | Workflow & Automation | 78 | — |
| [`chatgpt`](https://hlido.eu/reviews/chatgpt/) | ChatGPT | Chat & Companion | 90 | — |
| [`character-ai`](https://hlido.eu/reviews/character-ai/) | Character.AI | Chat & Companion | 53 | — |
| [`chatwithads`](https://hlido.eu/reviews/chatwithads/) | ChatWithAds | AI Agent | 78 | — |
| [`claude-ai`](https://hlido.eu/reviews/claude-ai/) | Claude.ai | Chat & Companion | 53 | — |
| [`codeium`](https://hlido.eu/reviews/codeium/) | Codeium | Coding | 65 | — |
| [`continue-dev`](https://hlido.eu/reviews/continue-dev/) | Continue | Coding | 75 | — |
| [`cohere`](https://hlido.eu/reviews/cohere/) | Cohere | Chat & Companion | 78 | — |
| [`crewai`](https://hlido.eu/reviews/crewai/) | CrewAI | Frameworks & Eval | 90 | — |
| [`datagrout`](https://hlido.eu/reviews/datagrout/) | DataGrout | AI Agent | 40 | — |
| [`dust-tt`](https://hlido.eu/reviews/dust-tt/) | Dust | Workflow & Automation | 90 | — |
| [`descript`](https://hlido.eu/reviews/descript/) | Descript | Voice | 65 | — |
| [`elevenlabs`](https://hlido.eu/reviews/elevenlabs/) | ElevenLabs | Voice | 78 | — |
| [`flux-bfl`](https://hlido.eu/reviews/flux-bfl/) | FLUX (Black Forest Labs) | Image & Design | 65 | — |
| [`flowith`](https://hlido.eu/reviews/flowith/) | Flowith | Workflow & Automation | 78 | — |
| [`fireworks-ai`](https://hlido.eu/reviews/fireworks-ai/) | Fireworks AI | Infrastructure | 90 | — |
| [`gemini`](https://hlido.eu/reviews/gemini/) | Gemini | Chat & Companion | 53 | — |
| [`github-copilot`](https://hlido.eu/reviews/github-copilot/) | GitHub Copilot | Coding | 90 | — |
| [`glean`](https://hlido.eu/reviews/glean/) | Glean | Research | 65 | — |
| [`helicone`](https://hlido.eu/reviews/helicone/) | Helicone | Frameworks & Eval | 90 | — |
| [`groq`](https://hlido.eu/reviews/groq/) | Groq | Infrastructure | 78 | — |
| [`heygen`](https://hlido.eu/reviews/heygen/) | HeyGen | Voice | 78 | — |
| [`humanloop`](https://hlido.eu/reviews/humanloop/) | Humanloop | Frameworks & Eval | 40 | — |
| [`ideogram`](https://hlido.eu/reviews/ideogram/) | Ideogram | Image & Design | 40 | — |
| [`inflection-pi`](https://hlido.eu/reviews/inflection-pi/) | Inflection Pi | Chat & Companion | 53 | — |
| [`jasper`](https://hlido.eu/reviews/jasper/) | Jasper | Marketing & Content | 90 | — |
| [`krea`](https://hlido.eu/reviews/krea/) | Krea | Image & Design | 78 | — |
| [`langchain`](https://hlido.eu/reviews/langchain/) | LangChain | Frameworks & Eval | 90 | — |
| [`langsmith`](https://hlido.eu/reviews/langsmith/) | LangSmith | Frameworks & Eval | 53 | — |
| [`leonardo-ai`](https://hlido.eu/reviews/leonardo-ai/) | Leonardo AI | Image & Design | 78 | — |
| [`llamaindex`](https://hlido.eu/reviews/llamaindex/) | LlamaIndex | Frameworks & Eval | 78 | — |
| [`lovable`](https://hlido.eu/reviews/lovable/) | Lovable | Coding | 78 | — |
| [`mem-ai`](https://hlido.eu/reviews/mem-ai/) | Mem | Productivity | 90 | — |
| [`microsoft-copilot`](https://hlido.eu/reviews/microsoft-copilot/) | Microsoft Copilot | Chat & Companion | 53 | — |
| [`midjourney`](https://hlido.eu/reviews/midjourney/) | Midjourney | Image & Design | 53 | — |
| [`mendable`](https://hlido.eu/reviews/mendable/) | Mendable | Research | 78 | — |
| [`mistral-le-chat`](https://hlido.eu/reviews/mistral-le-chat/) | Mistral Le Chat | Chat & Companion | 40 | — |
| [`notion-ai`](https://hlido.eu/reviews/notion-ai/) | Notion AI | Research | 65 | — |
| [`murf-ai`](https://hlido.eu/reviews/murf-ai/) | Murf AI | Voice | 65 | — |
| [`nyx`](https://hlido.eu/reviews/nyx/) | Nyx | AI Agent | 40 | — |
| [`openai-operator`](https://hlido.eu/reviews/openai-operator/) | OpenAI Operator | Infrastructure | 65 | — |
| [`openrouter`](https://hlido.eu/reviews/openrouter/) | OpenRouter | Infrastructure | 78 | — |
| [`phind`](https://hlido.eu/reviews/phind/) | Phind | Chat & Companion | 40 | — |
| [`pika`](https://hlido.eu/reviews/pika/) | Pika | Image & Design | 40 | — |
| [`otter-ai`](https://hlido.eu/reviews/otter-ai/) | Otter.ai | Productivity | 90 | — |
| [`pydantic-ai`](https://hlido.eu/reviews/pydantic-ai/) | Pydantic AI | Frameworks & Eval | 78 | — |
| [`reflect-app`](https://hlido.eu/reviews/reflect-app/) | Reflect | Productivity | 65 | — |
| [`read-ai`](https://hlido.eu/reviews/read-ai/) | Read AI | Productivity | 78 | — |
| [`resemble-ai`](https://hlido.eu/reviews/resemble-ai/) | Resemble AI | Voice | 78 | — |
| [`replit-agent`](https://hlido.eu/reviews/replit-agent/) | Replit Agent | Coding | 90 | — |
| [`relevance-ai`](https://hlido.eu/reviews/relevance-ai/) | Relevance AI | Workflow & Automation | 90 | — |
| [`runway`](https://hlido.eu/reviews/runway/) | Runway | Image & Design | 78 | — |
| [`sonarly`](https://hlido.eu/reviews/sonarly/) | Sonarly | AI Agent | 53 | — |
| [`retool-agents`](https://hlido.eu/reviews/retool-agents/) | Retool Agents | Workflow & Automation | 78 | — |
| [`stability-ai`](https://hlido.eu/reviews/stability-ai/) | Stability AI | Image & Design | 90 | — |
| [`sourcegraph-cody`](https://hlido.eu/reviews/sourcegraph-cody/) | Sourcegraph Cody | Coding | 90 | — |
| [`stack-ai`](https://hlido.eu/reviews/stack-ai/) | Stack AI | Workflow & Automation | 78 | — |
| [`suno`](https://hlido.eu/reviews/suno/) | Suno | Voice | 53 | — |
| [`superhuman`](https://hlido.eu/reviews/superhuman/) | Superhuman | Productivity | 78 | — |
| [`synthesia`](https://hlido.eu/reviews/synthesia/) | Synthesia | Voice | 90 | — |
| [`tabnine`](https://hlido.eu/reviews/tabnine/) | Tabnine | Coding | 90 | — |
| [`tana`](https://hlido.eu/reviews/tana/) | Tana | Productivity | 65 | — |
| [`tavus`](https://hlido.eu/reviews/tavus/) | Tavus | Voice | 78 | — |
| [`v0`](https://hlido.eu/reviews/v0/) | v0 | Coding | 76 | — |
| [`together-ai`](https://hlido.eu/reviews/together-ai/) | Together AI | Infrastructure | 65 | — |
| [`vercel-ai-sdk`](https://hlido.eu/reviews/vercel-ai-sdk/) | Vercel AI SDK | Frameworks & Eval | 78 | — |
| [`vellum-ai`](https://hlido.eu/reviews/vellum-ai/) | Vellum | Frameworks & Eval | 78 | — |
| [`you-com`](https://hlido.eu/reviews/you-com/) | You.com | Chat & Companion | 78 | — |
| [`writer-com`](https://hlido.eu/reviews/writer-com/) | Writer | Marketing & Content | 78 | — |
| [`zapier-central`](https://hlido.eu/reviews/zapier-central/) | Zapier Central | Workflow & Automation | 90 | — |
| [`bland-ai`](https://hlido.eu/reviews/bland-ai/) | Bland AI | Voice | 78 | — |
| [`retell-ai`](https://hlido.eu/reviews/retell-ai/) | Retell AI | Voice | 90 | — |
| [`vapi-ai`](https://hlido.eu/reviews/vapi-ai/) | Vapi | Voice | 90 | — |
| [`deepgram`](https://hlido.eu/reviews/deepgram/) | Deepgram | Voice | 90 | — |
| [`assemblyai`](https://hlido.eu/reviews/assemblyai/) | AssemblyAI | Voice | 90 | — |
| [`hume-ai`](https://hlido.eu/reviews/hume-ai/) | Hume AI | Voice | 65 | — |
| [`daily-co`](https://hlido.eu/reviews/daily-co/) | Daily | Voice | 90 | — |
| [`livekit`](https://hlido.eu/reviews/livekit/) | LiveKit | Voice | 78 | — |
| [`speechmatics`](https://hlido.eu/reviews/speechmatics/) | Speechmatics | Voice | 78 | — |
| [`rev-ai`](https://hlido.eu/reviews/rev-ai/) | Rev AI | Voice | 78 | — |
| [`salesloft`](https://hlido.eu/reviews/salesloft/) | Salesloft | Customer Experience | 78 | — |
| [`chorus-ai`](https://hlido.eu/reviews/chorus-ai/) | Chorus | Customer Experience | 65 | — |
| [`outreach-io`](https://hlido.eu/reviews/outreach-io/) | Outreach | Customer Experience | 65 | — |
| [`gong-io`](https://hlido.eu/reviews/gong-io/) | Gong | Customer Experience | 78 | — |
| [`apollo-io`](https://hlido.eu/reviews/apollo-io/) | Apollo.io | Customer Experience | 40 | — |
| [`clay-com`](https://hlido.eu/reviews/clay-com/) | Clay | Customer Experience | 90 | — |
| [`regie-ai`](https://hlido.eu/reviews/regie-ai/) | Regie AI | Customer Experience | 78 | — |
| [`instantly-ai`](https://hlido.eu/reviews/instantly-ai/) | Instantly | Customer Experience | 90 | — |
| [`smartlead`](https://hlido.eu/reviews/smartlead/) | Smartlead | Customer Experience | 78 | — |
| [`lavender-ai`](https://hlido.eu/reviews/lavender-ai/) | Lavender | Customer Experience | 78 | — |
| [`kore-ai`](https://hlido.eu/reviews/kore-ai/) | Kore.ai | Customer Experience | 65 | — |
| [`ada-cx`](https://hlido.eu/reviews/ada-cx/) | Ada | Customer Experience | 72 | — |
| [`ultimate-ai`](https://hlido.eu/reviews/ultimate-ai/) | Ultimate | Customer Experience | 65 | — |
| [`intercom-fin`](https://hlido.eu/reviews/intercom-fin/) | Intercom Fin | Customer Experience | 65 | — |
| [`forethought`](https://hlido.eu/reviews/forethought/) | Forethought | Customer Experience | 90 | — |
| [`cresta`](https://hlido.eu/reviews/cresta/) | Cresta | Customer Experience | 75 | — |
| [`netomi`](https://hlido.eu/reviews/netomi/) | Netomi | Customer Experience | 53 | — |
| [`cognigy`](https://hlido.eu/reviews/cognigy/) | Cognigy | Customer Experience | 78 | — |
| [`devin-cognition`](https://hlido.eu/reviews/devin-cognition/) | Devin (Cognition) | Coding | 65 | — |
| [`openhands`](https://hlido.eu/reviews/openhands/) | OpenHands | Coding | 90 | — |
| [`sweep-ai`](https://hlido.eu/reviews/sweep-ai/) | Sweep | Coding | 90 | — |
| [`openinterpreter`](https://hlido.eu/reviews/openinterpreter/) | Open Interpreter | Coding | 78 | — |
| [`metagpt`](https://hlido.eu/reviews/metagpt/) | MetaGPT | Coding | 65 | — |
| [`gpt-engineer`](https://hlido.eu/reviews/gpt-engineer/) | GPT Engineer | Coding | 78 | — |
| [`agentgpt`](https://hlido.eu/reviews/agentgpt/) | AgentGPT | Coding | 65 | — |
| [`autogen-studio`](https://hlido.eu/reviews/autogen-studio/) | AutoGen Studio | Coding | 78 | — |
| [`smol-ai`](https://hlido.eu/reviews/smol-ai/) | Smol Developer | Coding | 40 | — |
| [`superagi`](https://hlido.eu/reviews/superagi/) | SuperAGI | Coding | 78 | — |
| [`plandex`](https://hlido.eu/reviews/plandex/) | Plandex | Coding | 65 | — |
| [`zed-ai`](https://hlido.eu/reviews/zed-ai/) | Zed AI | Coding | 90 | — |
| [`scite-ai`](https://hlido.eu/reviews/scite-ai/) | Scite | Research | 78 | — |
| [`consensus-app`](https://hlido.eu/reviews/consensus-app/) | Consensus | Research | 53 | — |
| [`scholarcy`](https://hlido.eu/reviews/scholarcy/) | Scholarcy | Research | 78 | — |
| [`exa-ai`](https://hlido.eu/reviews/exa-ai/) | Exa | Research | 90 | — |
| [`kagi`](https://hlido.eu/reviews/kagi/) | Kagi | Research | 78 | — |
| [`andi-search`](https://hlido.eu/reviews/andi-search/) | Andi Search | Research | 65 | — |
| [`komo-ai`](https://hlido.eu/reviews/komo-ai/) | Komo | Research | 53 | — |
| [`notebooklm`](https://hlido.eu/reviews/notebooklm/) | NotebookLM | Research | 65 | — |
| [`hebbia`](https://hlido.eu/reviews/hebbia/) | Hebbia | Research | 78 | — |
| [`casetext`](https://hlido.eu/reviews/casetext/) | Casetext | Specialized verticals | 40 | — |
| [`ironclad`](https://hlido.eu/reviews/ironclad/) | Ironclad | Specialized verticals | 78 | — |
| [`harvey-ai`](https://hlido.eu/reviews/harvey-ai/) | Harvey | Specialized verticals | 78 | — |
| [`evisort`](https://hlido.eu/reviews/evisort/) | Evisort | Specialized verticals | 53 | — |
| [`spellbook-legal`](https://hlido.eu/reviews/spellbook-legal/) | Spellbook | Specialized verticals | 90 | — |
| [`luminance`](https://hlido.eu/reviews/luminance/) | Luminance | Specialized verticals | 65 | — |
| [`hippocratic-ai`](https://hlido.eu/reviews/hippocratic-ai/) | Hippocratic AI | Specialized verticals | 53 | — |
| [`suki-ai`](https://hlido.eu/reviews/suki-ai/) | Suki | Specialized verticals | 90 | — |
| [`glass-health`](https://hlido.eu/reviews/glass-health/) | Glass Health | Specialized verticals | 78 | — |
| [`abridge`](https://hlido.eu/reviews/abridge/) | Abridge | Specialized verticals | 75 | — |
| [`nabla`](https://hlido.eu/reviews/nabla/) | Nabla | Specialized verticals | 78 | — |
| [`mutiny`](https://hlido.eu/reviews/mutiny/) | Mutiny | Marketing & Content | 65 | — |
| [`persado`](https://hlido.eu/reviews/persado/) | Persado | Marketing & Content | 53 | — |
| [`optimizely-opal`](https://hlido.eu/reviews/optimizely-opal/) | Optimizely Opal | Marketing & Content | 90 | — |
| [`smartwriter`](https://hlido.eu/reviews/smartwriter/) | Smartwriter | Marketing & Content | 65 | — |
| [`rytr`](https://hlido.eu/reviews/rytr/) | Rytr | Marketing & Content | 78 | — |
| [`simplified`](https://hlido.eu/reviews/simplified/) | Simplified | Marketing & Content | 78 | — |
| [`khanmigo`](https://hlido.eu/reviews/khanmigo/) | Khanmigo | Specialized verticals | 53 | — |
| [`quizizz`](https://hlido.eu/reviews/quizizz/) | Quizizz AI | Specialized verticals | 65 | — |
| [`magic-school`](https://hlido.eu/reviews/magic-school/) | MagicSchool | Specialized verticals | 78 | — |
| [`brisk-teaching`](https://hlido.eu/reviews/brisk-teaching/) | Brisk Teaching | Specialized verticals | 78 | — |
| [`galileo-ai-design`](https://hlido.eu/reviews/galileo-ai-design/) | Galileo (Design) | Image & Design | 40 | — |
| [`uizard`](https://hlido.eu/reviews/uizard/) | Uizard | Image & Design | 78 | — |
| [`framer-ai`](https://hlido.eu/reviews/framer-ai/) | Framer AI | Image & Design | 65 | — |
| [`browser-base`](https://hlido.eu/reviews/browser-base/) | Browserbase | Infrastructure | 78 | — |
| [`recraft-ai`](https://hlido.eu/reviews/recraft-ai/) | Recraft | Image & Design | 78 | — |
| [`figma-make`](https://hlido.eu/reviews/figma-make/) | Figma Make | Image & Design | 65 | — |
| [`anchor-browser`](https://hlido.eu/reviews/anchor-browser/) | Anchor Browser | Infrastructure | 65 | — |
| [`simular`](https://hlido.eu/reviews/simular/) | Simular | Infrastructure | 78 | — |
| [`scrapybara`](https://hlido.eu/reviews/scrapybara/) | Scrapybara | Infrastructure | 78 | — |
| [`multion`](https://hlido.eu/reviews/multion/) | MultiOn | Infrastructure | 53 | — |
| [`browser-use`](https://hlido.eu/reviews/browser-use/) | Browser Use | Infrastructure | 78 | — |
| [`pinecone`](https://hlido.eu/reviews/pinecone/) | Pinecone | Infrastructure | 90 | — |
| [`weaviate`](https://hlido.eu/reviews/weaviate/) | Weaviate | Infrastructure | 90 | — |
| [`voyage-ai`](https://hlido.eu/reviews/voyage-ai/) | Voyage AI | Infrastructure | 65 | — |
| [`jina-ai`](https://hlido.eu/reviews/jina-ai/) | Jina AI | Infrastructure | 65 | — |
| [`qdrant`](https://hlido.eu/reviews/qdrant/) | Qdrant | Infrastructure | 90 | — |
| [`hex-tech`](https://hlido.eu/reviews/hex-tech/) | Hex | Infrastructure | 78 | — |
| [`julius-ai`](https://hlido.eu/reviews/julius-ai/) | Julius | Infrastructure | 78 | — |
| [`n8n`](https://hlido.eu/reviews/n8n/) | n8n | Workflow & Automation | 90 | — |
| [`make-com`](https://hlido.eu/reviews/make-com/) | Make | Workflow & Automation | 90 | — |
| [`activepieces`](https://hlido.eu/reviews/activepieces/) | Activepieces | Workflow & Automation | 72 | — |
| [`zapier`](https://hlido.eu/reviews/zapier/) | Zapier | Workflow & Automation | 90 | — |
| [`integrately`](https://hlido.eu/reviews/integrately/) | Integrately | Workflow & Automation | 90 | — |
| [`langflow`](https://hlido.eu/reviews/langflow/) | Langflow | Workflow & Automation | 78 | — |
| [`flowiseai`](https://hlido.eu/reviews/flowiseai/) | Flowise | Workflow & Automation | 78 | — |
| [`pipedream`](https://hlido.eu/reviews/pipedream/) | Pipedream | Workflow & Automation | 90 | — |
| [`magic-dev`](https://hlido.eu/reviews/magic-dev/) | Magic | Coding | 53 | — |
| [`dify-ai`](https://hlido.eu/reviews/dify-ai/) | Dify | Workflow & Automation | 78 | — |
| [`poolside-ai`](https://hlido.eu/reviews/poolside-ai/) | Poolside | Coding | 65 | — |
| [`contextual-ai`](https://hlido.eu/reviews/contextual-ai/) | Contextual AI | Research | 75 | — |
| [`langfuse`](https://hlido.eu/reviews/langfuse/) | Langfuse | Frameworks & Eval | 90 | — |
| [`traceloop`](https://hlido.eu/reviews/traceloop/) | Traceloop | Frameworks & Eval | 90 | — |
| [`promptlayer`](https://hlido.eu/reviews/promptlayer/) | PromptLayer | Frameworks & Eval | 65 | — |
| [`ragas`](https://hlido.eu/reviews/ragas/) | Ragas | Frameworks & Eval | 78 | — |
| [`trulens`](https://hlido.eu/reviews/trulens/) | TruLens | Frameworks & Eval | 65 | — |
| [`portkey-ai`](https://hlido.eu/reviews/portkey-ai/) | Portkey | Frameworks & Eval | 90 | — |
| [`inkeep`](https://hlido.eu/reviews/inkeep/) | Inkeep | Customer Experience | 78 | — |
| [`kapa-ai`](https://hlido.eu/reviews/kapa-ai/) | Kapa AI | Customer Experience | 90 | — |
| [`guru-ai`](https://hlido.eu/reviews/guru-ai/) | Guru | Productivity | 78 | — |
| [`self-operating-computer`](https://hlido.eu/reviews/self-operating-computer/) | Self-Operating Computer | Workflow & Automation | 90 | — |
| [`skyvern-ai`](https://hlido.eu/reviews/skyvern-ai/) | Skyvern | Infrastructure | 65 | — |
| [`fathom-video`](https://hlido.eu/reviews/fathom-video/) | Fathom | Productivity | 65 | — |
| [`fellow-app`](https://hlido.eu/reviews/fellow-app/) | Fellow | Productivity | 78 | — |
| [`clay-relationship`](https://hlido.eu/reviews/clay-relationship/) | Clay (relationships) | Productivity | 65 | — |
| [`spinach-ai`](https://hlido.eu/reviews/spinach-ai/) | Spinach | Productivity | 78 | — |
| [`anyscale`](https://hlido.eu/reviews/anyscale/) | Anyscale | Infrastructure | 90 | — |
| [`baseten`](https://hlido.eu/reviews/baseten/) | Baseten | Infrastructure | 78 | — |
| [`modal-com`](https://hlido.eu/reviews/modal-com/) | Modal | Infrastructure | 90 | — |
| [`ollama`](https://hlido.eu/reviews/ollama/) | Ollama | Infrastructure | 90 | — |
| [`replicate`](https://hlido.eu/reviews/replicate/) | Replicate | Infrastructure | 78 | — |
| [`lmstudio`](https://hlido.eu/reviews/lmstudio/) | LM Studio | Infrastructure | 65 | — |
| [`deepseek-chat`](https://hlido.eu/reviews/deepseek-chat/) | DeepSeek | Chat & Companion | 78 | — |
| [`xai-grok`](https://hlido.eu/reviews/xai-grok/) | Grok (xAI) | Chat & Companion | 65 | — |
| [`hugging-face`](https://hlido.eu/reviews/hugging-face/) | HuggingFace | Infrastructure | 78 | — |
| [`qwen-chat`](https://hlido.eu/reviews/qwen-chat/) | Qwen Chat | Chat & Companion | 40 | — |
| [`kimi-moonshot`](https://hlido.eu/reviews/kimi-moonshot/) | Kimi (Moonshot) | Chat & Companion | 53 | — |
| [`replika`](https://hlido.eu/reviews/replika/) | Replika | Chat & Companion | 53 | — |
| [`yi-01ai`](https://hlido.eu/reviews/yi-01ai/) | Yi (01.AI) | Chat & Companion | 53 | — |
| [`scenario-gg`](https://hlido.eu/reviews/scenario-gg/) | Scenario | Image & Design | 65 | — |
| [`playground-ai`](https://hlido.eu/reviews/playground-ai/) | Playground AI | Image & Design | 78 | — |
| [`nightcafe`](https://hlido.eu/reviews/nightcafe/) | NightCafe | Image & Design | 53 | — |
| [`luma-genie`](https://hlido.eu/reviews/luma-genie/) | Luma Genie | Image & Design | 65 | — |
| [`meshy-ai`](https://hlido.eu/reviews/meshy-ai/) | Meshy | Image & Design | 90 | — |
| [`clickup-ai`](https://hlido.eu/reviews/clickup-ai/) | ClickUp AI | Productivity | 78 | — |
| [`monday-ai`](https://hlido.eu/reviews/monday-ai/) | Monday AI | Productivity | 53 | — |
| [`smartsheet-ai`](https://hlido.eu/reviews/smartsheet-ai/) | Smartsheet AI | Productivity | 90 | — |
| [`openai-realtime`](https://hlido.eu/reviews/openai-realtime/) | OpenAI Realtime | Infrastructure | 90 | — |
| [`perplexity-api`](https://hlido.eu/reviews/perplexity-api/) | Perplexity API | Infrastructure | 90 | — |
| [`tavily-api`](https://hlido.eu/reviews/tavily-api/) | Tavily | Infrastructure | 78 | — |
| [`airtable-ai`](https://hlido.eu/reviews/airtable-ai/) | Airtable AI | Productivity | 72 | — |
| [`dia-browser`](https://hlido.eu/reviews/dia-browser/) | Dia (The Browser Company) | Infrastructure | 53 | — |
| [`arc-browser`](https://hlido.eu/reviews/arc-browser/) | Arc Browser | Infrastructure | 78 | — |
| [`aria-opera`](https://hlido.eu/reviews/aria-opera/) | Aria (Opera) | Infrastructure | 65 | — |
| [`serpapi`](https://hlido.eu/reviews/serpapi/) | SerpAPI | Infrastructure | 78 | — |
| [`brave-leo`](https://hlido.eu/reviews/brave-leo/) | Brave Leo | Infrastructure | 78 | — |
| [`kensho`](https://hlido.eu/reviews/kensho/) | Kensho | Specialized verticals | 53 | — |
| [`ravenpack`](https://hlido.eu/reviews/ravenpack/) | RavenPack | Specialized verticals | 65 | — |
| [`alphasense`](https://hlido.eu/reviews/alphasense/) | AlphaSense | Specialized verticals | 78 | — |
| [`paradigm-ai`](https://hlido.eu/reviews/paradigm-ai/) | Paradigm | Productivity | 78 | — |
| [`lutra`](https://hlido.eu/reviews/lutra/) | Lutra | Workflow & Automation | 78 | — |
| [`you-com-search`](https://hlido.eu/reviews/you-com-search/) | You.com Search | Research | 40 | — |
| [`perplexity-shopping`](https://hlido.eu/reviews/perplexity-shopping/) | Perplexity Shopping | Customer Experience | 40 | — |
| [`elastic-quote`](https://hlido.eu/reviews/elastic-quote/) | Elastic Quote | Research | 78 | — |
| [`seek-ai`](https://hlido.eu/reviews/seek-ai/) | Seek AI | Infrastructure | 53 | — |
| [`rabbit-r1`](https://hlido.eu/reviews/rabbit-r1/) | Rabbit R1 | AI Agent | 65 | — |
| [`humane-ai-pin`](https://hlido.eu/reviews/humane-ai-pin/) | Humane AI Pin | AI Agent | 53 | — |
| [`chai-research`](https://hlido.eu/reviews/chai-research/) | Chai | Chat & Companion | 53 | — |
| [`janitor-ai`](https://hlido.eu/reviews/janitor-ai/) | Janitor AI | Chat & Companion | 53 | — |
| [`snorkel-ai`](https://hlido.eu/reviews/snorkel-ai/) | Snorkel AI | Infrastructure | 65 | — |
| [`botpress`](https://hlido.eu/reviews/botpress/) | Botpress | Customer Experience | 90 | — |
| [`rasa`](https://hlido.eu/reviews/rasa/) | Rasa | Customer Experience | 78 | — |
| [`voiceflow`](https://hlido.eu/reviews/voiceflow/) | Voiceflow | Voice | 90 | — |
| [`automa-app`](https://hlido.eu/reviews/automa-app/) | Automa | Infrastructure | 78 | — |
| [`nebius`](https://hlido.eu/reviews/nebius/) | Nebius | Infrastructure | 40 | — |
| [`openrouter-models`](https://hlido.eu/reviews/openrouter-models/) | OpenRouter Models | Infrastructure | 78 | — |
| [`lambda-labs`](https://hlido.eu/reviews/lambda-labs/) | Lambda Labs | Infrastructure | 78 | — |
| [`recogni`](https://hlido.eu/reviews/recogni/) | Recogni | Infrastructure | 53 | — |
| [`deepinfra`](https://hlido.eu/reviews/deepinfra/) | DeepInfra | Infrastructure | 78 | — |
| [`haystack-deepset`](https://hlido.eu/reviews/haystack-deepset/) | Haystack | Workflow & Automation | 78 | — |
| [`agno`](https://hlido.eu/reviews/agno/) | Agno | Workflow & Automation | 70 | — |
| [`griptape`](https://hlido.eu/reviews/griptape/) | Griptape | Workflow & Automation | 78 | — |
| [`livekit-agents`](https://hlido.eu/reviews/livekit-agents/) | LiveKit Agents | Voice | 78 | — |
| [`swiggy-ai`](https://hlido.eu/reviews/swiggy-ai/) | Swiggy AI | AI Agent | 53 | — |
| [`zebrium`](https://hlido.eu/reviews/zebrium/) | Zebrium | Frameworks & Eval | 65 | — |
| [`openai-agent-sdk`](https://hlido.eu/reviews/openai-agent-sdk/) | OpenAI Agent SDK | Workflow & Automation | 65 | — |
| [`kling-ai`](https://hlido.eu/reviews/kling-ai/) | Kling | Image & Design | 53 | — |
| [`hailuo-ai`](https://hlido.eu/reviews/hailuo-ai/) | Hailuo AI | Image & Design | 53 | — |
| [`vidu-ai`](https://hlido.eu/reviews/vidu-ai/) | Vidu | Image & Design | 65 | — |
| [`pixverse`](https://hlido.eu/reviews/pixverse/) | Pixverse | Image & Design | 65 | — |
| [`playphone-ai`](https://hlido.eu/reviews/playphone-ai/) | PlayPhone AI | Voice | 40 | — |
| [`camb-ai`](https://hlido.eu/reviews/camb-ai/) | Camb AI | Voice | 78 | — |
| [`warmly-ai`](https://hlido.eu/reviews/warmly-ai/) | Warmly | Customer Experience | 78 | — |
| [`hubspot-clearbit`](https://hlido.eu/reviews/hubspot-clearbit/) | HubSpot Clearbit | Customer Experience | 75 | — |
| [`clari`](https://hlido.eu/reviews/clari/) | Clari | Customer Experience | 78 | — |
| [`opal-ai`](https://hlido.eu/reviews/opal-ai/) | Opal | Productivity | 40 | — |
| [`swebench`](https://hlido.eu/reviews/swebench/) | SWE-bench Leaderboards | AI Agent | 65 | — |
| [`bondai`](https://hlido.eu/reviews/bondai/) | Meet BondAI | BondAI | AI Agent | 78 | — |
| [`agentrunner`](https://hlido.eu/reviews/agentrunner/) | AgentRunner | Productivity | 50 | — |
| [`base44-superagents`](https://hlido.eu/reviews/base44-superagents/) | Base44 Superagents | Productivity | 70 | — |
| [`emergent-wingman`](https://hlido.eu/reviews/emergent-wingman/) | Emergent Wingman | Productivity | 40 | — |
| [`gauge`](https://hlido.eu/reviews/gauge/) | Gauge | Marketing | 60 | — |
| [`goose`](https://hlido.eu/reviews/goose/) | GooseAI | AI Agent | 78 | — |
| [`intent-augment-code`](https://hlido.eu/reviews/intent-augment-code/) | Intent (Augment Code) | Coding | 40 | — |
| [`openfang`](https://hlido.eu/reviews/openfang/) | OpenFang | Productivity | 40 | — |
| [`pensieve`](https://hlido.eu/reviews/pensieve/) | Pensieve | Research | 60 | — |
| [`heightsplatform`](https://hlido.eu/reviews/heightsplatform/) | AI Online Course Creation Platform - Heights AI 2 Features | AI Agent | 65 | — |
| [`writesonic`](https://hlido.eu/reviews/writesonic/) | Writesonic | Marketing & Content | 90 | — |
| [`flux-imessage-agents`](https://hlido.eu/reviews/flux-imessage-agents/) | Flux | Productivity | 90 | — |
| [`ai2sql`](https://hlido.eu/reviews/ai2sql/) | SQL Query Builder & Generator - AI Powered Database Assistant | AI Agent | 50 | FADING |
| [`headlinesai-pro`](https://hlido.eu/reviews/headlinesai-pro/) | Free AI Title Generator – Get Catchy & SEO-Friendly Titles | NetusAI | Marketing & Content | 50 | FADING |
| [`canary`](https://hlido.eu/reviews/canary/) | Canary | Coding | 90 | — |
| [`cal-com`](https://hlido.eu/reviews/cal-com/) | Cal.com AI | Productivity | 90 | — |
| [`aiforgoogleslides`](https://hlido.eu/reviews/aiforgoogleslides/) | AI for Google Slides - Free Google Slides AI tool | Coding | 50 | FADING |
| [`app-rapidtextai`](https://hlido.eu/reviews/app-rapidtextai/) | RapidTextAI - Advanced AI article generator, Content, and Image Generation Tools | Image & Design | 65 | — |
| [`avatarai-me`](https://hlido.eu/reviews/avatarai-me/) | AI Avatar Generator - Create Custom AI Avatars of Yourself | Professional Photo Shoots with AI | Image & Design | 65 | — |
| [`aws-amazon`](https://hlido.eu/reviews/aws-amazon/) | Agentic Coding Experience - Amazon Q Developer - AWS | Coding | 50 | — |
| [`chatwithcloud`](https://hlido.eu/reviews/chatwithcloud/) | ChatWithCloud - Chat with your AWS Cloud from Terminal | Chat & Companion | 78 | — |
| [`astra`](https://hlido.eu/reviews/astra/) | Astra | Productivity | 40 | — |
| [`civitai`](https://hlido.eu/reviews/civitai/) | Civitai | Share your models | AI Agent | 65 | — |
| [`enact`](https://hlido.eu/reviews/enact/) | Enact | Productivity | 90 | — |
| [`crossnode`](https://hlido.eu/reviews/crossnode/) | Crossnode | Productivity | 90 | — |
| [`fathom-3-0`](https://hlido.eu/reviews/fathom-3-0/) | Fathom 3.0 | Productivity | 40 | — |
| [`d-id`](https://hlido.eu/reviews/d-id/) | D-ID | The #1 Choice for AI Generated Video Creation Platform | Image & Design | 78 | — |
| [`imgcmd`](https://hlido.eu/reviews/imgcmd/) | imgcmd | Image & Design | 73 | — |
| [`far-site`](https://hlido.eu/reviews/far-site/) | FARSITE - Government Contract Compliance Software | AI Agent | 53 | — |
| [`leap`](https://hlido.eu/reviews/leap/) | Leap | Coding | 73 | — |
| [`editgpt`](https://hlido.eu/reviews/editgpt/) | Proofread, edit and track changes to your content using ChatGPT. | editGPT | Chat & Companion | 78 | — |
| [`hubspot-breeze-prospecting-agent`](https://hlido.eu/reviews/hubspot-breeze-prospecting-agent/) | HubSpot Breeze Prospecting Agent | Productivity | 57 | — |
| [`flexapp`](https://hlido.eu/reviews/flexapp/) | AI Mobile App Designer — Beautiful UI in Minutes | GenDesigns | Image & Design | 65 | — |
| [`get-meetgeek`](https://hlido.eu/reviews/get-meetgeek/) | MeetGeek | AI Note Taker and Meeting Assistant | Workflow & Automation | 50 | FADING |
| [`get-murf`](https://hlido.eu/reviews/get-murf/) | Free AI Voice Generator & Text to Speech Online | Murf AI | Voice | 65 | — |
| [`rewind-ai`](https://hlido.eu/reviews/rewind-ai/) | Rewind AI | AI Agent | 40 | — |
| [`adobe-firefly-ai-assistant`](https://hlido.eu/reviews/adobe-firefly-ai-assistant/) | Adobe Firefly AI Assistant | Image & Design | 73 | — |
| [`clide`](https://hlido.eu/reviews/clide/) | Clide | Coding | 40 | — |
| [`mercury`](https://hlido.eu/reviews/mercury/) | Mercury | Productivity | 90 | — |
| [`nelly`](https://hlido.eu/reviews/nelly/) | Nelly | Productivity | 90 | — |
| [`opencode`](https://hlido.eu/reviews/opencode/) | OpenCode | Coding | 90 | — |
| [`openagents`](https://hlido.eu/reviews/openagents/) | OpenAgents | Productivity | 73 | — |
| [`origami`](https://hlido.eu/reviews/origami/) | Origami | Productivity | 90 | — |
| [`raydian`](https://hlido.eu/reviews/raydian/) | Raydian | Coding | 90 | — |
| [`smooth-cli`](https://hlido.eu/reviews/smooth-cli/) | Smooth CLI | Coding | 73 | — |
| [`startfa-st`](https://hlido.eu/reviews/startfa-st/) | Startfa.st | AI Agent | 90 | — |
| [`stackai-auto-agents`](https://hlido.eu/reviews/stackai-auto-agents/) | StackAI Auto-Agents | Productivity | 73 | — |
| [`tracium`](https://hlido.eu/reviews/tracium/) | Tracium | Infrastructure | 90 | — |
| [`verdent`](https://hlido.eu/reviews/verdent/) | Verdent | Coding | 90 | — |
| [`cleocode-lafs`](https://hlido.eu/reviews/cleocode-lafs/) | @cleocode/lafs | Coding | 57 | — |
| [`tencent-ai-agent-server`](https://hlido.eu/reviews/tencent-ai-agent-server/) | @tencent-ai/agent-server | Coding | 73 | — |
| [`beeai-framework`](https://hlido.eu/reviews/beeai-framework/) | beeai-framework | Coding | 73 | — |
| [`contextgraph-agent`](https://hlido.eu/reviews/contextgraph-agent/) | @contextgraph/agent | AI Agent | 73 | — |
| [`voltagent-core`](https://hlido.eu/reviews/voltagent-core/) | @voltagent/core | Coding | 73 | — |
| [`build-skill`](https://hlido.eu/reviews/build-skill/) | build-skill | Coding | 73 | — |
| [`oci-generativeaiagent`](https://hlido.eu/reviews/oci-generativeaiagent/) | oci-generativeaiagent | Coding | 90 | — |
| [`21st-extension-toolbar`](https://hlido.eu/reviews/21st-extension-toolbar/) | @21st-extension/toolbar | Coding | 73 | — |
| [`paperclipai`](https://hlido.eu/reviews/paperclipai/) | paperclipai | Coding | 73 | — |
| [`winsznx-lend402`](https://hlido.eu/reviews/winsznx-lend402/) | @winsznx/lend402 | Coding | 90 | — |
| [`lleverage-ai-agent-threads`](https://hlido.eu/reviews/lleverage-ai-agent-threads/) | @lleverage-ai/agent-threads | Coding | 73 | — |
| [`openkrew`](https://hlido.eu/reviews/openkrew/) | openkrew | Coding | 90 | — |
| [`clipboard-health-ai-rules`](https://hlido.eu/reviews/clipboard-health-ai-rules/) | @clipboard-health/ai-rules | Coding | 57 | — |
| [`jay-ai-agent`](https://hlido.eu/reviews/jay-ai-agent/) | @jay-ai/agent | Coding | 73 | — |
| [`alice-space-alice`](https://hlido.eu/reviews/alice-space-alice/) | @alice_space/alice | Coding | 73 | — |
| [`contractspec-lib-ai-agent`](https://hlido.eu/reviews/contractspec-lib-ai-agent/) | @contractspec/lib.ai-agent | Coding | 90 | — |
| [`pocketflow`](https://hlido.eu/reviews/pocketflow/) | pocketflow | Frameworks & Eval | 90 | — |
| [`neoagent`](https://hlido.eu/reviews/neoagent/) | neoagent | Coding | 73 | — |
| [`frumu-tandem-client`](https://hlido.eu/reviews/frumu-tandem-client/) | @frumu/tandem-client | AI Agent | 90 | — |
| [`create-bubblelab-app`](https://hlido.eu/reviews/create-bubblelab-app/) | create-bubblelab-app | Coding | 73 | — |
| [`nori-ai-cli`](https://hlido.eu/reviews/nori-ai-cli/) | nori-ai-cli | Coding | 73 | — |
| [`ff-labs-fff-bun`](https://hlido.eu/reviews/ff-labs-fff-bun/) | @ff-labs/fff-bun | Coding | 73 | — |
| [`mypensieve`](https://hlido.eu/reviews/mypensieve/) | mypensieve | AI Agent | 73 | — |
| [`openduo-duoduo`](https://hlido.eu/reviews/openduo-duoduo/) | @openduo/duoduo | AI Agent | 90 | — |
| [`compilr-dev-agents`](https://hlido.eu/reviews/compilr-dev-agents/) | @compilr-dev/agents | Coding | 90 | — |
| [`beav3r-sdk`](https://hlido.eu/reviews/beav3r-sdk/) | @beav3r/sdk | AI Agent | 73 | — |
| [`leaper-agent`](https://hlido.eu/reviews/leaper-agent/) | leaper-agent | AI Agent | 90 | — |
| [`mcp-abap-adt-openai-llm`](https://hlido.eu/reviews/mcp-abap-adt-openai-llm/) | @mcp-abap-adt/openai-llm | Coding | 73 | — |
| [`mcp-abap-adt-anthropic-llm`](https://hlido.eu/reviews/mcp-abap-adt-anthropic-llm/) | @mcp-abap-adt/anthropic-llm | Coding | 73 | — |
| [`donobu`](https://hlido.eu/reviews/donobu/) | donobu | Coding | 90 | — |
| [`mcp-abap-adt-deepseek-llm`](https://hlido.eu/reviews/mcp-abap-adt-deepseek-llm/) | @mcp-abap-adt/deepseek-llm | Coding | 73 | — |
| [`higgsfield-cli`](https://hlido.eu/reviews/higgsfield-cli/) | @higgsfield/cli | Coding | 90 | — |
| [`mcp-abap-adt-sap-aicore-llm`](https://hlido.eu/reviews/mcp-abap-adt-sap-aicore-llm/) | @mcp-abap-adt/sap-aicore-llm | Coding | 73 | — |
| [`mcp-abap-adt-qdrant-rag`](https://hlido.eu/reviews/mcp-abap-adt-qdrant-rag/) | @mcp-abap-adt/qdrant-rag | Coding | 73 | — |
| [`mcp-abap-adt-openai-embedder`](https://hlido.eu/reviews/mcp-abap-adt-openai-embedder/) | @mcp-abap-adt/openai-embedder | Coding | 73 | — |
| [`elvatis-com-aahp-runner`](https://hlido.eu/reviews/elvatis-com-aahp-runner/) | @elvatis_com/aahp-runner | AI Agent | 73 | — |
| [`pathcourse-langchain`](https://hlido.eu/reviews/pathcourse-langchain/) | @pathcourse/langchain | AI Agent | 73 | — |
| [`nopeek`](https://hlido.eu/reviews/nopeek/) | nopeek | Coding | 90 | — |
| [`sym-bot-xmesh-agent`](https://hlido.eu/reviews/sym-bot-xmesh-agent/) | @sym-bot/xmesh-agent | AI Agent | 73 | — |
| [`mcp-abap-adt-pg-vector-rag`](https://hlido.eu/reviews/mcp-abap-adt-pg-vector-rag/) | @mcp-abap-adt/pg-vector-rag | Coding | 73 | — |
| [`studio-foundation-runner`](https://hlido.eu/reviews/studio-foundation-runner/) | @studio-foundation/runner | Coding | 90 | — |
| [`ipads-skvm-skvm`](https://hlido.eu/reviews/ipads-skvm-skvm/) | @ipads-skvm/skvm | Coding | 90 | — |
| [`mcp-abap-adt-ollama-embedder`](https://hlido.eu/reviews/mcp-abap-adt-ollama-embedder/) | @mcp-abap-adt/ollama-embedder | Coding | 73 | — |
| [`luxyie-ai-cli`](https://hlido.eu/reviews/luxyie-ai-cli/) | luxyie.ai-cli | Coding | 90 | — |
| [`alpha-cli-toolkit`](https://hlido.eu/reviews/alpha-cli-toolkit/) | alpha-cli-toolkit | AI Agent | 90 | — |
| [`possumtech-antlrmap`](https://hlido.eu/reviews/possumtech-antlrmap/) | @possumtech/antlrmap | Coding | 90 | — |
| [`llmtxt`](https://hlido.eu/reviews/llmtxt/) | llmtxt | Coding | 73 | — |
| [`wu529778790-open-im`](https://hlido.eu/reviews/wu529778790-open-im/) | @wu529778790/open-im | Coding | 73 | — |
| [`herdctl`](https://hlido.eu/reviews/herdctl/) | herdctl | AI Agent | 73 | — |
| [`claude-gombwe`](https://hlido.eu/reviews/claude-gombwe/) | claude-gombwe | AI Agent | 73 | — |
| [`create-lancelot`](https://hlido.eu/reviews/create-lancelot/) | create-lancelot | AI Agent | 73 | — |
| [`pdh-ai-cli`](https://hlido.eu/reviews/pdh-ai-cli/) | pdh-ai-cli | Coding | 90 | — |
| [`orion-ai`](https://hlido.eu/reviews/orion-ai/) | orion-ai | Coding | 73 | — |
| [`benjam16-umbrella`](https://hlido.eu/reviews/benjam16-umbrella/) | @benjam16/umbrella | AI Agent | 73 | — |
| [`leixusam-foundry`](https://hlido.eu/reviews/leixusam-foundry/) | @leixusam/foundry | AI Agent | 90 | — |
| [`fireqa-agent`](https://hlido.eu/reviews/fireqa-agent/) | fireqa-agent | Coding | 90 | — |
| [`postbridge-langchain`](https://hlido.eu/reviews/postbridge-langchain/) | postbridge-langchain | Frameworks & Eval | 90 | — |
| [`aliasjeff-acli`](https://hlido.eu/reviews/aliasjeff-acli/) | @aliasjeff/acli | Coding | 90 | — |
| [`extend-ai-cli-darwin-arm64`](https://hlido.eu/reviews/extend-ai-cli-darwin-arm64/) | @extend-ai/cli-darwin-arm64 | Coding | 73 | — |
| [`extend-ai-cli-win32-x64`](https://hlido.eu/reviews/extend-ai-cli-win32-x64/) | @extend-ai/cli-win32-x64 | Coding | 73 | — |
| [`eetr-agent-streemr`](https://hlido.eu/reviews/eetr-agent-streemr/) | @eetr/agent-streemr | Frameworks & Eval | 90 | — |
| [`u0z-zero-graph`](https://hlido.eu/reviews/u0z-zero-graph/) | @u0z/zero-graph | Frameworks & Eval | 90 | — |
| [`langchain-langgraph-supervisor`](https://hlido.eu/reviews/langchain-langgraph-supervisor/) | @langchain/langgraph-supervisor | Frameworks & Eval | 73 | — |
| [`deepagents`](https://hlido.eu/reviews/deepagents/) | deepagents | Frameworks & Eval | 73 | — |
| [`create-langgraph`](https://hlido.eu/reviews/create-langgraph/) | create-langgraph | Frameworks & Eval | 73 | — |
| [`langchain-langgraph-sdk`](https://hlido.eu/reviews/langchain-langgraph-sdk/) | @langchain/langgraph-sdk | Frameworks & Eval | 73 | — |
| [`langchain-openai`](https://hlido.eu/reviews/langchain-openai/) | @langchain/openai | Frameworks & Eval | 57 | — |
| [`langchain-mcp-adapters`](https://hlido.eu/reviews/langchain-mcp-adapters/) | @langchain/mcp-adapters | Frameworks & Eval | 57 | — |
| [`langchain-community`](https://hlido.eu/reviews/langchain-community/) | @langchain/community | Frameworks & Eval | 73 | — |
| [`langchain-agentfolio`](https://hlido.eu/reviews/langchain-agentfolio/) | langchain-agentfolio | Frameworks & Eval | 90 | — |
| [`langchain-google-genai`](https://hlido.eu/reviews/langchain-google-genai/) | @langchain/google-genai | Frameworks & Eval | 57 | — |
| [`langchain-langgraph-swarm`](https://hlido.eu/reviews/langchain-langgraph-swarm/) | @langchain/langgraph-swarm | Frameworks & Eval | 73 | — |
| [`elelem`](https://hlido.eu/reviews/elelem/) | elelem | Frameworks & Eval | 90 | — |
| [`stripe-agent-toolkit`](https://hlido.eu/reviews/stripe-agent-toolkit/) | @stripe/agent-toolkit | Frameworks & Eval | 73 | — |
| [`langchain-anthropic`](https://hlido.eu/reviews/langchain-anthropic/) | @langchain/anthropic | Frameworks & Eval | 57 | — |
| [`osohq-langchain`](https://hlido.eu/reviews/osohq-langchain/) | @osohq/langchain | Frameworks & Eval | 90 | — |
| [`langchain-aws`](https://hlido.eu/reviews/langchain-aws/) | @langchain/aws | Frameworks & Eval | 57 | — |
| [`langchain-copilotkit`](https://hlido.eu/reviews/langchain-copilotkit/) | langchain-copilotkit | Frameworks & Eval | 90 | — |
| [`langchain-textsplitters`](https://hlido.eu/reviews/langchain-textsplitters/) | @langchain/textsplitters | Frameworks & Eval | 57 | — |
| [`langchainhub`](https://hlido.eu/reviews/langchainhub/) | langchainhub | Frameworks & Eval | 73 | — |
| [`pocketflow-js`](https://hlido.eu/reviews/pocketflow-js/) | pocketflow-js | Frameworks & Eval | 90 | — |
| [`serverless`](https://hlido.eu/reviews/serverless/) | serverless | Frameworks & Eval | 90 | — |
| [`livekit-agents-plugin-openai`](https://hlido.eu/reviews/livekit-agents-plugin-openai/) | @livekit/agents-plugin-openai | Frameworks & Eval | 73 | — |
| [`backpackflow`](https://hlido.eu/reviews/backpackflow/) | backpackflow | Frameworks & Eval | 73 | — |
| [`pocketflow-core`](https://hlido.eu/reviews/pocketflow-core/) | @pocketflow/core | Frameworks & Eval | 90 | — |
| [`llm-dev-ops-llm-schema-registry-integrations`](https://hlido.eu/reviews/llm-dev-ops-llm-schema-registry-integrations/) | @llm-dev-ops/llm-schema-registry-integrations | Frameworks & Eval | 73 | — |
| [`open-mercato-ai-assistant`](https://hlido.eu/reviews/open-mercato-ai-assistant/) | @open-mercato/ai-assistant | Frameworks & Eval | 73 | — |
| [`litechain`](https://hlido.eu/reviews/litechain/) | litechain | Frameworks & Eval | 90 | — |
| [`ax-llm-ax`](https://hlido.eu/reviews/ax-llm-ax/) | @ax-llm/ax | Frameworks & Eval | 73 | — |
| [`llm-spend-guard`](https://hlido.eu/reviews/llm-spend-guard/) | llm-spend-guard | Frameworks & Eval | 90 | — |
| [`hopfield`](https://hlido.eu/reviews/hopfield/) | hopfield | Frameworks & Eval | 73 | — |
| [`outputai-llm`](https://hlido.eu/reviews/outputai-llm/) | @outputai/llm | Frameworks & Eval | 90 | — |
| [`mastra-core`](https://hlido.eu/reviews/mastra-core/) | @mastra/core | Frameworks & Eval | 90 | — |
| [`claude-skills-library`](https://hlido.eu/reviews/claude-skills-library/) | claude-skills-library | Frameworks & Eval | 90 | — |
| [`nlux-react`](https://hlido.eu/reviews/nlux-react/) | @nlux/react | Frameworks & Eval | 90 | — |
| [`vulnbuster`](https://hlido.eu/reviews/vulnbuster/) | VulnBuster | AI Agent | 40 | — |
| [`gradio-agentchatbot`](https://hlido.eu/reviews/gradio-agentchatbot/) | gradio_agentchatbot | Chat & Companion | 57 | — |
| [`site-agent`](https://hlido.eu/reviews/site-agent/) | site-agent | AI Agent | 57 | — |
| [`cs-agent`](https://hlido.eu/reviews/cs-agent/) | cs-agent | Chat & Companion | 57 | — |
| [`referatai`](https://hlido.eu/reviews/referatai/) | referatai | Chat & Companion | 57 | — |
| [`openai-chatgpt-turbo-ui`](https://hlido.eu/reviews/openai-chatgpt-turbo-ui/) | OpenAI_chatgpt-turbo-UI | Chat & Companion | 40 | — |
| [`xylaria`](https://hlido.eu/reviews/xylaria/) | Xylaria | Chat & Companion | 40 | — |
| [`fara-browseruse`](https://hlido.eu/reviews/fara-browseruse/) | Fara-BrowserUse | AI Agent | 57 | — |
| [`fleetmind-in-action`](https://hlido.eu/reviews/fleetmind-in-action/) | fleetmind-in-action | AI Agent | 40 | — |
| [`ai-recruiting-agent`](https://hlido.eu/reviews/ai-recruiting-agent/) | AI_Recruiting_Agent | AI Agent | 57 | — |
| [`chatgpt-assistant`](https://hlido.eu/reviews/chatgpt-assistant/) | ChatGPT-Assistant | Chat & Companion | 57 | — |
| [`hy-embodied-0-5`](https://hlido.eu/reviews/hy-embodied-0-5/) | HY-Embodied-0.5 | Chat & Companion | 57 | — |
| [`pixdiet`](https://hlido.eu/reviews/pixdiet/) | PixDiet | Chat & Companion | 40 | — |
| [`self-chat`](https://hlido.eu/reviews/self-chat/) | self-chat | Chat & Companion | 57 | — |
| [`graphstrike`](https://hlido.eu/reviews/graphstrike/) | graphstrike | AI Agent | 57 | — |
| [`shillrank-agent`](https://hlido.eu/reviews/shillrank-agent/) | shillrank-agent | AI Agent | 40 | — |
| [`finario-ai-agent-and-mcp`](https://hlido.eu/reviews/finario-ai-agent-and-mcp/) | Finario-AI-Agent-and-MCP | AI Agent | 57 | — |
| [`orynxml-backend`](https://hlido.eu/reviews/orynxml-backend/) | orynxml-backend | Chat & Companion | 57 | — |
| [`synergy-ai`](https://hlido.eu/reviews/synergy-ai/) | Synergy-ai | Chat & Companion | 57 | — |
| [`huggingface-chatbot-cascade`](https://hlido.eu/reviews/huggingface-chatbot-cascade/) | Huggingface_Chatbot_Cascade | Chat & Companion | 57 | — |
| [`babel-1-world-engine`](https://hlido.eu/reviews/babel-1-world-engine/) | Babel-1-World-Engine | AI Agent | 57 | — |
| [`api`](https://hlido.eu/reviews/api/) | API | Chat & Companion | 57 | — |
| [`paper-survey-agent`](https://hlido.eu/reviews/paper-survey-agent/) | paper-survey-agent | AI Agent | 40 | — |
| [`metaenv`](https://hlido.eu/reviews/metaenv/) | MetaEnv | AI Agent | 57 | — |
| [`admissions-env`](https://hlido.eu/reviews/admissions-env/) | admissions_env | AI Agent | 57 | — |
| [`flight-rebooking`](https://hlido.eu/reviews/flight-rebooking/) | flight-rebooking | AI Agent | 40 | — |
| [`meeting-scheduler-openenv`](https://hlido.eu/reviews/meeting-scheduler-openenv/) | meeting-scheduler-openenv | AI Agent | 57 | — |
| [`itil-reflexion-agent`](https://hlido.eu/reviews/itil-reflexion-agent/) | itil-reflexion-agent | AI Agent | 57 | — |
| [`champion-council-private`](https://hlido.eu/reviews/champion-council-private/) | Champion_Council_private | AI Agent | 57 | — |
| [`siteagent`](https://hlido.eu/reviews/siteagent/) | siteagent | AI Agent | 57 | — |
| [`pixdiet-old-mistral`](https://hlido.eu/reviews/pixdiet-old-mistral/) | PixDiet-Old-Mistral | Chat & Companion | 40 | — |
| [`pubmed-rag`](https://hlido.eu/reviews/pubmed-rag/) | pubmed_rag | Chat & Companion | 40 | — |
| [`trip-planner-v1-tools`](https://hlido.eu/reviews/trip-planner-v1-tools/) | trip_planner_v1_tools | Chat & Companion | 57 | — |
| [`finflow`](https://hlido.eu/reviews/finflow/) | FinFLow | Chat & Companion | 57 | — |
| [`insurellmrag`](https://hlido.eu/reviews/insurellmrag/) | insurellmrag | Chat & Companion | 40 | — |
| [`gpt`](https://hlido.eu/reviews/gpt/) | gpt | Chat & Companion | 40 | — |
| [`linguaicoach`](https://hlido.eu/reviews/linguaicoach/) | linguAIcoach | Chat & Companion | 57 | — |
| [`scholarbot`](https://hlido.eu/reviews/scholarbot/) | ScholarBot | Chat & Companion | 57 | — |
| [`irtaza`](https://hlido.eu/reviews/irtaza/) | irtaza | Chat & Companion | 57 | — |
| [`sentiment-chat-app`](https://hlido.eu/reviews/sentiment-chat-app/) | sentiment-chat-app | Chat & Companion | 57 | — |
| [`chatgks`](https://hlido.eu/reviews/chatgks/) | chatGKS | Chat & Companion | 57 | — |
| [`research-ai-assistant`](https://hlido.eu/reviews/research-ai-assistant/) | Research_AI_Assistant | Chat & Companion | 57 | — |
| [`dataengenv`](https://hlido.eu/reviews/dataengenv/) | DataEngEnv | AI Agent | 57 | — |
| [`multi-cloud-optimizer`](https://hlido.eu/reviews/multi-cloud-optimizer/) | multi_cloud_optimizer | AI Agent | 57 | — |
| [`customer-support-env`](https://hlido.eu/reviews/customer-support-env/) | customer-support-env | AI Agent | 57 | — |
| [`clinical-trial-optimizer`](https://hlido.eu/reviews/clinical-trial-optimizer/) | clinical-trial-optimizer | AI Agent | 57 | — |
| [`macro-signal-env`](https://hlido.eu/reviews/macro-signal-env/) | macro-signal-env | AI Agent | 57 | — |
| [`data-cleaning-env`](https://hlido.eu/reviews/data-cleaning-env/) | data-cleaning-env | AI Agent | 57 | — |
| [`agentic-customer-experience-simulation`](https://hlido.eu/reviews/agentic-customer-experience-simulation/) | Agentic_Customer_Experience_Simulation | AI Agent | 57 | — |
| [`devops-incident-response`](https://hlido.eu/reviews/devops-incident-response/) | devops-incident-response | AI Agent | 57 | — |
| [`auditrix`](https://hlido.eu/reviews/auditrix/) | Auditrix | AI Agent | 57 | — |
| [`my-env`](https://hlido.eu/reviews/my-env/) | my-env | AI Agent | 57 | — |
| [`adaptive-backend-traffic-controller`](https://hlido.eu/reviews/adaptive-backend-traffic-controller/) | adaptive-backend-traffic-controller | AI Agent | 57 | — |
| [`messy-data-triage-gym`](https://hlido.eu/reviews/messy-data-triage-gym/) | messy-data-triage-gym | AI Agent | 57 | — |
| [`smartgrid-rl-env-backup`](https://hlido.eu/reviews/smartgrid-rl-env-backup/) | smartgrid-rl-env-backup | AI Agent | 57 | — |
| [`incidentops-openenv`](https://hlido.eu/reviews/incidentops-openenv/) | incidentops-openenv | AI Agent | 57 | — |
| [`last-mile-logistics-env-v1`](https://hlido.eu/reviews/last-mile-logistics-env-v1/) | last-mile-logistics-env-v1 | AI Agent | 57 | — |
| [`code-review-env`](https://hlido.eu/reviews/code-review-env/) | code-review-env | AI Agent | 57 | — |
| [`shopeasy-support-gym`](https://hlido.eu/reviews/shopeasy-support-gym/) | shopeasy-support-gym | AI Agent | 57 | — |
| [`cybersoc-arena`](https://hlido.eu/reviews/cybersoc-arena/) | cybersoc-arena | AI Agent | 57 | — |
| [`graphstrike-model-training`](https://hlido.eu/reviews/graphstrike-model-training/) | graphstrike-model-training | AI Agent | 57 | — |
| [`training-space`](https://hlido.eu/reviews/training-space/) | training-space | AI Agent | 57 | — |
| [`compliance-gym-lending`](https://hlido.eu/reviews/compliance-gym-lending/) | compliance-gym-lending | AI Agent | 57 | — |
| [`saas-audit-env`](https://hlido.eu/reviews/saas-audit-env/) | saas-audit-env | AI Agent | 57 | — |
| [`policyqa-commandrplus-rag-agent`](https://hlido.eu/reviews/policyqa-commandrplus-rag-agent/) | PolicyQA-CommandRPlus-RAG-Agent | AI Agent | 57 | — |
| [`radify`](https://hlido.eu/reviews/radify/) | radify | AI Agent | 57 | — |
| [`osogritvoice`](https://hlido.eu/reviews/osogritvoice/) | OSOGRITVOICE | AI Agent | 40 | — |
| [`gritvoice45`](https://hlido.eu/reviews/gritvoice45/) | GRITVOICE45 | AI Agent | 57 | — |
| [`atharva`](https://hlido.eu/reviews/atharva/) | atharva | AI Agent | 57 | — |
| [`gaia-eval-l1-20`](https://hlido.eu/reviews/gaia-eval-l1-20/) | gaia-eval-l1-20 | AI Agent | 57 | — |
| [`basic-agent-training`](https://hlido.eu/reviews/basic-agent-training/) | Basic_Agent_Training | AI Agent | 57 | — |
| [`voice-ocr-agent`](https://hlido.eu/reviews/voice-ocr-agent/) | Voice_OCR_Agent | AI Agent | 40 | — |
| [`dynamic-function-calling-agent`](https://hlido.eu/reviews/dynamic-function-calling-agent/) | Dynamic-Function-Calling-Agent | AI Agent | 57 | — |
| [`home-assistant-diagnostics-agent`](https://hlido.eu/reviews/home-assistant-diagnostics-agent/) | Home-Assistant-Diagnostics-Agent | AI Agent | 57 | — |
| [`localspark-ai`](https://hlido.eu/reviews/localspark-ai/) | localspark-ai | AI Agent | 57 | — |
| [`quiz-agent4`](https://hlido.eu/reviews/quiz-agent4/) | quiz-agent4 | AI Agent | 57 | — |
| [`quiz-agent3`](https://hlido.eu/reviews/quiz-agent3/) | quiz-agent3 | AI Agent | 40 | — |
| [`tdsfinal`](https://hlido.eu/reviews/tdsfinal/) | tdsfinal | AI Agent | 57 | — |
| [`lavent-marketing-agent`](https://hlido.eu/reviews/lavent-marketing-agent/) | lavent-marketing-agent | AI Agent | 57 | — |
| [`quiz-agent1`](https://hlido.eu/reviews/quiz-agent1/) | quiz-agent1 | AI Agent | 40 | — |
| [`tdsproject2`](https://hlido.eu/reviews/tdsproject2/) | TDSPROJECT2 | AI Agent | 57 | — |
| [`hs-unit4-agent`](https://hlido.eu/reviews/hs-unit4-agent/) | hs-unit4-agent | AI Agent | 57 | — |
| [`voice-agent`](https://hlido.eu/reviews/voice-agent/) | Voice_Agent | AI Agent | 57 | — |
| [`magic-patterns`](https://hlido.eu/reviews/magic-patterns/) | Magic Patterns | Image & Design | 90 | — |
| [`bolt-new-v2`](https://hlido.eu/reviews/bolt-new-v2/) | Bolt.new (StackBlitz) | Coding | 90 | — |
| [`coplay`](https://hlido.eu/reviews/coplay/) | Coplay | Coding | 90 | — |
| [`sema4-ai`](https://hlido.eu/reviews/sema4-ai/) | Sema4.ai | Workflow & Automation | 90 | — |
| [`runner-h-h-company`](https://hlido.eu/reviews/runner-h-h-company/) | Runner H (H Company) | AI Agent | 90 | — |
| [`proxy-convergence`](https://hlido.eu/reviews/proxy-convergence/) | Proxy (Convergence AI) | AI Agent | 40 | — |
| [`replit-ai-agent`](https://hlido.eu/reviews/replit-ai-agent/) | Replit AI (Ghostwriter) | Coding | 90 | — |
| [`genie-cosine`](https://hlido.eu/reviews/genie-cosine/) | Genie (Cosine AI) | Coding | 90 | — |
| [`phonely`](https://hlido.eu/reviews/phonely/) | Phonely | Voice | 90 | — |
| [`sierra-platform`](https://hlido.eu/reviews/sierra-platform/) | Sierra (CX agent platform) | Customer Experience | 90 | — |
| [`parloa`](https://hlido.eu/reviews/parloa/) | Parloa | Customer Experience | 90 | — |
| [`decagon-platform`](https://hlido.eu/reviews/decagon-platform/) | Decagon AI Agent | Customer Experience | 90 | — |
| [`11x-ai`](https://hlido.eu/reviews/11x-ai/) | 11x.ai | Productivity | 90 | — |
| [`artisan-ai`](https://hlido.eu/reviews/artisan-ai/) | Artisan AI | Productivity | 73 | — |
| [`rox-ai`](https://hlido.eu/reviews/rox-ai/) | Rox | Productivity | 90 | — |
| [`elicit-research`](https://hlido.eu/reviews/elicit-research/) | Elicit | Research | 90 | — |
| [`granola-ai`](https://hlido.eu/reviews/granola-ai/) | Granola AI | Productivity | 90 | — |
| [`autogen-microsoft`](https://hlido.eu/reviews/autogen-microsoft/) | Microsoft AutoGen | Frameworks & Eval | 90 | — |
| [`arize-phoenix`](https://hlido.eu/reviews/arize-phoenix/) | Arize Phoenix | Frameworks & Eval | 90 | — |
| [`agentops-ai`](https://hlido.eu/reviews/agentops-ai/) | AgentOps | Frameworks & Eval | 90 | — |
| [`hyperbolic-ai`](https://hlido.eu/reviews/hyperbolic-ai/) | Hyperbolic | Infrastructure | 90 | — |
| [`mem-0-ai`](https://hlido.eu/reviews/mem-0-ai/) | Mem0 AI | Infrastructure | 90 | — |
| [`langgraph-platform`](https://hlido.eu/reviews/langgraph-platform/) | LangGraph Platform | Frameworks & Eval | 90 | — |
| [`weaviate-platform`](https://hlido.eu/reviews/weaviate-platform/) | Weaviate Cloud | Infrastructure | 90 | — |
| [`cline-2`](https://hlido.eu/reviews/cline-2/) | Cline (latest) | Coding | 90 | — |
| [`warp-ai-terminal`](https://hlido.eu/reviews/warp-ai-terminal/) | Warp AI Terminal | Coding | 90 | — |
| [`roocode`](https://hlido.eu/reviews/roocode/) | Roo Code | Coding | 73 | — |
| [`ampcode`](https://hlido.eu/reviews/ampcode/) | AmpCode by Sourcegraph | Coding | 90 | — |
| [`lex-page`](https://hlido.eu/reviews/lex-page/) | Lex | Image & Design | 85 | STEADY |
| [`openai`](https://hlido.eu/reviews/openai/) | API Platform | OpenAI | Coding | 90 | VITAL |
| [`getnudgeai`](https://hlido.eu/reviews/getnudgeai/) | Best AI Scribe and Coding Platform for Clinical AI Solutions - Nudge AI | Productivity | 90 | VITAL |
| [`photoguruai`](https://hlido.eu/reviews/photoguruai/) | The Best AI Headshots Generator | Chat & Companion | 75 | STEADY |
| [`nurgo-software`](https://hlido.eu/reviews/nurgo-software/) | BrainSoup: build an AI team that works for you | Workflow & Automation | 70 | STEADY |
| [`plantphotoai`](https://hlido.eu/reviews/plantphotoai/) | Best free AI-crafted plant photos | PlantPhotoAI | AI Agent | 70 | STEADY |
| [`hyperwriteai`](https://hlido.eu/reviews/hyperwriteai/) | HyperWrite | AI Writing Assistant | Voice | 85 | STEADY |
| [`magicstudio`](https://hlido.eu/reviews/magicstudio/) | Create images from text | AI Image Generator by Magic Studio | Image & Design | 90 | VITAL |
| [`chatgptwriter`](https://hlido.eu/reviews/chatgptwriter/) | Jetwriter AI: Personalized AI Writing Assistant for Chrome, Desktop & Mobile. Free to Try. | Research | 50 | FADING |
| [`airkit`](https://hlido.eu/reviews/airkit/) | Agentforce: The AI Agent Platform | Salesforce | Customer Experience | 50 | FADING |
| [`try-sanebox`](https://hlido.eu/reviews/try-sanebox/) | SaneBox | Email Management for Any Inbox | Productivity | 90 | VITAL |
| [`theunwindai`](https://hlido.eu/reviews/theunwindai/) | unwind ai | AI Agent | 70 | STEADY |
| [`spellapp`](https://hlido.eu/reviews/spellapp/) | AI Document Generator | Spell AI | AI Agent | 90 | VITAL |
| [`sitegpt`](https://hlido.eu/reviews/sitegpt/) | SiteGPT - Make AI your expert customer support agent | Chat & Companion | 90 | VITAL |
| [`planttattoosai`](https://hlido.eu/reviews/planttattoosai/) | AI Plant Tattoo Generator | PlantTattoosAI | Image & Design | 70 | STEADY |
| [`republiclabs`](https://hlido.eu/reviews/republiclabs/) | RepublicLabs.ai | Generate images and videos from AI Generative models | Image & Design | 80 | STEADY |
| [`text2infographic`](https://hlido.eu/reviews/text2infographic/) | Text to Infographic — AI Infographic Generator | AI Agent | 85 | STEADY |
| [`publicprompts-art`](https://hlido.eu/reviews/publicprompts-art/) | Public Prompts - Free AI Prompts, Models & Resources | Workflow & Automation | 70 | STEADY |
| [`playgroundai`](https://hlido.eu/reviews/playgroundai/) | Free AI Design Tool: Logos, T-Shirts, Social Media - Playground | Image & Design | 75 | STEADY |
| [`prisma-ai`](https://hlido.eu/reviews/prisma-ai/) | Lensa - Prisma Labs | Image & Design | 70 | STEADY |
| [`robin-ai`](https://hlido.eu/reviews/robin-ai/) | Robin AI | Legal | 50 | FADING |
| [`browser-use-browser-harness`](https://hlido.eu/reviews/browser-use-browser-harness/) | browser-use/browser-harness | AI Agent | 40 | — |
| [`avadsa25-codec`](https://hlido.eu/reviews/avadsa25-codec/) | AVADSA25/codec | Coding | 40 | — |
| [`bitterbot-ai-bitterbot-desktop`](https://hlido.eu/reviews/bitterbot-ai-bitterbot-desktop/) | Bitterbot-AI/bitterbot-desktop | AI Agent | 40 | — |
| [`blockrunai-franklin`](https://hlido.eu/reviews/blockrunai-franklin/) | BlockRunAI/Franklin | AI Agent | 40 | — |
| [`cosmicstack-labs-mercury-agent`](https://hlido.eu/reviews/cosmicstack-labs-mercury-agent/) | cosmicstack-labs/mercury-agent | AI Agent | 40 | — |
| [`crisandrews-clawcode`](https://hlido.eu/reviews/crisandrews-clawcode/) | crisandrews/ClawCode | Coding | 40 | — |
| [`dimknaf-braindb`](https://hlido.eu/reviews/dimknaf-braindb/) | dimknaf/braindb | AI Agent | 40 | — |
| [`eggbrid2-mobileclaw`](https://hlido.eu/reviews/eggbrid2-mobileclaw/) | eggbrid2/mobileClaw | Workflow & Automation | 40 | — |
| [`ag2ai-ag2`](https://hlido.eu/reviews/ag2ai-ag2/) | ag2ai/ag2 | AI Agent | 50 | FADING |
| [`alibaba-page-agent`](https://hlido.eu/reviews/alibaba-page-agent/) | alibaba/page-agent | AI Agent | 40 | — |
| [`alibaba-spring-ai-alibaba`](https://hlido.eu/reviews/alibaba-spring-ai-alibaba/) | alibaba/spring-ai-alibaba | Coding | 40 | — |
| [`asheshgoplani-agent-deck`](https://hlido.eu/reviews/asheshgoplani-agent-deck/) | asheshgoplani/agent-deck | Coding | 40 | — |
| [`automaapp-automa`](https://hlido.eu/reviews/automaapp-automa/) | AutomaApp/automa | Workflow & Automation | 50 | FADING |
| [`beever-ai-beever-atlas`](https://hlido.eu/reviews/beever-ai-beever-atlas/) | Beever-AI/beever-atlas | AI Agent | 40 | — |
| [`browser-use-browser-use`](https://hlido.eu/reviews/browser-use-browser-use/) | browser-use/browser-use | Workflow & Automation | 40 | — |
| [`copilotkit-copilotkit`](https://hlido.eu/reviews/copilotkit-copilotkit/) | CopilotKit/CopilotKit | AI Agent | 40 | — |
| [`areal-project-areal`](https://hlido.eu/reviews/areal-project-areal/) | AReaL | AI Agent | 55 | — |
| [`cherryhq-cherry-studio`](https://hlido.eu/reviews/cherryhq-cherry-studio/) | Cherry Studio | Chat & Companion | 72 | — |
| [`clockless-org-html-anything`](https://hlido.eu/reviews/clockless-org-html-anything/) | html-anything | Coding | 65 | — |
| [`coderluii-holyclaude`](https://hlido.eu/reviews/coderluii-holyclaude/) | HolyClaude | Coding | 67 | — |
| [`aifordevelopers`](https://hlido.eu/reviews/aifordevelopers/) | AI for Developers | Coding | 57 | FADING |
| [`aidc-ai-comfyui-copilot`](https://hlido.eu/reviews/aidc-ai-comfyui-copilot/) | AIDC-AI/ComfyUI-Copilot | Image & Design | 82 | STEADY |
| [`erickong-aura-agent`](https://hlido.eu/reviews/erickong-aura-agent/) | erickong/aura-agent | AI Agent | 67 | FADING |
| [`esengine-deepseek-reasonix`](https://hlido.eu/reviews/esengine-deepseek-reasonix/) | esengine/DeepSeek-Reasonix | AI Agent | 50 | FADING |
| [`fazxes-claude-code`](https://hlido.eu/reviews/fazxes-claude-code/) | fazxes/Claude-code | Coding | 60 | FADING |
| [`genieincodebottle-generative-ai`](https://hlido.eu/reviews/genieincodebottle-generative-ai/) | genieincodebottle/generative-ai | Research | 80 | STEADY |
| [`gitlawb-openclaude`](https://hlido.eu/reviews/gitlawb-openclaude/) | openclaude | Coding | 72 | STEADY |
| [`gizclaw-flowcraft`](https://hlido.eu/reviews/gizclaw-flowcraft/) | GizClaw/flowcraft | Frameworks & Eval | 82 | STEADY |
| [`google-agents-cli`](https://hlido.eu/reviews/google-agents-cli/) | google/agents-cli | Frameworks & Eval | 80 | STEADY |
| [`gi-dellav-zerostack`](https://hlido.eu/reviews/gi-dellav-zerostack/) | gi-dellav/zerostack | Coding | 70 | STEADY |
| [`google-cloud-ai-agent-platform`](https://hlido.eu/reviews/google-cloud-ai-agent-platform/) | Google-Cloud-AI/agent-platform | Frameworks & Eval | 80 | STEADY |
| [`gptme-gptme`](https://hlido.eu/reviews/gptme-gptme/) | gptme/gptme | Coding | 75 | STEADY |
| [`gistai`](https://hlido.eu/reviews/gistai/) | Gist AI | Productivity | 63 | FADING |
| [`he-yufeng-corecoder`](https://hlido.eu/reviews/he-yufeng-corecoder/) | he-yufeng/CoreCoder | Coding | 70 | STEADY |
| [`graykode-abtop`](https://hlido.eu/reviews/graykode-abtop/) | graykode/abtop | Coding | 82 | STEADY |
| [`heymrun-heym`](https://hlido.eu/reviews/heymrun-heym/) | heymrun/heym | Workflow & Automation | 80 | STEADY |
| [`hello-qm-catgo-lrg`](https://hlido.eu/reviews/hello-qm-catgo-lrg/) | Hello-QM/catgo-LRG | Specialized verticals | 82 | STEADY |
| [`hkuds-deepcode`](https://hlido.eu/reviews/hkuds-deepcode/) | HKUDS/DeepCode | Coding | 90 | VITAL |
| [`hkuds-vibe-trading`](https://hlido.eu/reviews/hkuds-vibe-trading/) | Vibe-Trading | AI Agent | 76 | STEADY |
| [`hughyau-qiushi-skill`](https://hlido.eu/reviews/hughyau-qiushi-skill/) | Qiushi Skill | AI Agent | 61 | FADING |
| [`holaboss-ai-holaos`](https://hlido.eu/reviews/holaboss-ai-holaos/) | holaboss | AI Agent | 66 | FADING |
| [`hugohe3-ppt-master`](https://hlido.eu/reviews/hugohe3-ppt-master/) | hugohe3/ppt-master | Productivity | 80 | STEADY |
| [`itayinbarr-little-coder`](https://hlido.eu/reviews/itayinbarr-little-coder/) | itayinbarr/little-coder | Coding | 70 | STEADY |
| [`jackwener-opencli`](https://hlido.eu/reviews/jackwener-opencli/) | jackwener/OpenCLI | Workflow & Automation | 75 | STEADY |
| [`jeinlee1991-chinese-llm-benchmark`](https://hlido.eu/reviews/jeinlee1991-chinese-llm-benchmark/) | jeinlee1991/chinese-llm-benchmark | Frameworks & Eval | 70 | STEADY |
| [`jordanrendric-claude-video-vision`](https://hlido.eu/reviews/jordanrendric-claude-video-vision/) | jordanrendric/claude-video-vision | Coding | 82 | STEADY |
| [`langroid-langroid`](https://hlido.eu/reviews/langroid-langroid/) | langroid/langroid | Frameworks & Eval | 85 | STEADY |
| [`leon-ai-leon`](https://hlido.eu/reviews/leon-ai-leon/) | leon-ai/leon | Chat & Companion | 75 | STEADY |
| [`letta-ai-letta`](https://hlido.eu/reviews/letta-ai-letta/) | letta-ai/letta | Frameworks & Eval | 80 | STEADY |
| [`lsdefine-genericagent`](https://hlido.eu/reviews/lsdefine-genericagent/) | lsdefine/GenericAgent | AI Agent | 82 | STEADY |
| [`mai-with-u-maibot`](https://hlido.eu/reviews/mai-with-u-maibot/) | Mai-with-u/MaiBot | Coding | 75 | STEADY |
| [`manavarya09-design-extract`](https://hlido.eu/reviews/manavarya09-design-extract/) | Manavarya09/design-extract | Image & Design | 10 | FLATLINE |
| [`lucasrosati-claude-code-memory-setup`](https://hlido.eu/reviews/lucasrosati-claude-code-memory-setup/) | lucasrosati/claude-code-memory-setup | Coding | 82 | STEADY |
| [`mcp-brasil-mcp-brasil`](https://hlido.eu/reviews/mcp-brasil-mcp-brasil/) | Mcp-Brasil/mcp-brasil | Infrastructure | 82 | STEADY |
| [`microsoft-autogen`](https://hlido.eu/reviews/microsoft-autogen/) | microsoft/autogen | Frameworks & Eval | 80 | STEADY |
| [`memtensor-skills-vote`](https://hlido.eu/reviews/memtensor-skills-vote/) | SkillsVote | AI Agent | 64 | FADING |
| [`miomioos-mioisland`](https://hlido.eu/reviews/miomioos-mioisland/) | MioIsland | Coding | 71 | STEADY |
| [`minishlab-semble`](https://hlido.eu/reviews/minishlab-semble/) | MinishLab/semble | Coding | 85 | STEADY |
| [`myicor-mypka`](https://hlido.eu/reviews/myicor-mypka/) | myICOR | Productivity | 59 | FADING |
| [`nduckmink-arkon`](https://hlido.eu/reviews/nduckmink-arkon/) | nduckmink/arkon | MCP Server | 67 | FADING |
| [`neothecapt-redteamagent`](https://hlido.eu/reviews/neothecapt-redteamagent/) | NeoTheCapt/RedteamAgent | Coding | 73 | STEADY |
| [`nexu-io-html-anything`](https://hlido.eu/reviews/nexu-io-html-anything/) | HTML Anything | Coding | 74 | STEADY |
| [`portialabs`](https://hlido.eu/reviews/portialabs/) | Portia Labs (Rezonant) | Coding | 64 | — |
| [`nesquena-hermes-webui`](https://hlido.eu/reviews/nesquena-hermes-webui/) | nesquena/hermes-webui | AI Agent | 80 | STEADY |
| [`nocobase-nocobase`](https://hlido.eu/reviews/nocobase-nocobase/) | nocobase/nocobase | Workflow & Automation | 75 | STEADY |
| [`ogulcancelik-herdr`](https://hlido.eu/reviews/ogulcancelik-herdr/) | ogulcancelik/herdr | AI Agent | 75 | STEADY |
| [`omyarewar-phantom`](https://hlido.eu/reviews/omyarewar-phantom/) | OmYarewar/PHANTOM | Specialized verticals | 82 | STEADY |
| [`op7418-guizang-ppt-skill`](https://hlido.eu/reviews/op7418-guizang-ppt-skill/) | op7418/guizang-ppt-skill | Image & Design | 82 | STEADY |
| [`opensensenova-sensenova-skills`](https://hlido.eu/reviews/opensensenova-sensenova-skills/) | OpenSenseNova/SenseNova-Skills | Workflow & Automation | 73 | STEADY |
| [`pacifio-cersei`](https://hlido.eu/reviews/pacifio-cersei/) | pacifio/cersei | AI Agent | 70 | STEADY |
| [`pattern-ai-labs-agentcall`](https://hlido.eu/reviews/pattern-ai-labs-agentcall/) | pattern-ai-labs/agentcall | Voice | 50 | FADING |
| [`patterai-patter`](https://hlido.eu/reviews/patterai-patter/) | PatterAI/Patter | Voice | 80 | STEADY |
| [`pguso-ai-agents-from-scratch`](https://hlido.eu/reviews/pguso-ai-agents-from-scratch/) | pguso/ai-agents-from-scratch | AI Agent | 80 | STEADY |
| [`ryancodrai-turbovec`](https://hlido.eu/reviews/ryancodrai-turbovec/) | RyanCodrai/turbovec | AI Agent | 85 | STEADY |
| [`writewithlaika`](https://hlido.eu/reviews/writewithlaika/) | Write with Laika | AI Agent | 38 | — |
| [`santifer-career-ops`](https://hlido.eu/reviews/santifer-career-ops/) | santifer/career-ops | Coding | 50 | FADING |
| [`storybloq-storybloq`](https://hlido.eu/reviews/storybloq-storybloq/) | Storybloq/storybloq | Coding | 70 | STEADY |
| [`synapseorch-ai-synapse-ai`](https://hlido.eu/reviews/synapseorch-ai-synapse-ai/) | synapseorch-ai/synapse-ai | Infrastructure | 50 | FADING |
| [`swarmclawai-swarmvault`](https://hlido.eu/reviews/swarmclawai-swarmvault/) | swarmclawai/swarmvault | Coding | 75 | STEADY |
| [`thinkwatchproject-thinkwatch`](https://hlido.eu/reviews/thinkwatchproject-thinkwatch/) | ThinkWatchProject/ThinkWatch | Infrastructure | 75 | STEADY |
| [`trycua-cua`](https://hlido.eu/reviews/trycua-cua/) | trycua/cua | Infrastructure | 85 | STEADY |
| [`the-pocket-pocketflow`](https://hlido.eu/reviews/the-pocket-pocketflow/) | The-Pocket/PocketFlow | AI Agent | 85 | STEADY |
| [`vectifyai-openkb`](https://hlido.eu/reviews/vectifyai-openkb/) | VectifyAI/OpenKB | AI Agent | 70 | STEADY |
| [`wanshuiyin-auto-claude-code-research-in-sleep`](https://hlido.eu/reviews/wanshuiyin-auto-claude-code-research-in-sleep/) | wanshuiyin/Auto-claude-code-research-in-sleep | Research | 82 | STEADY |
| [`usewhale-deepseek-code-whale`](https://hlido.eu/reviews/usewhale-deepseek-code-whale/) | usewhale/DeepSeek-Code-Whale | Coding | 85 | STEADY |
| [`withkynam-vibecode-pro-max-kit`](https://hlido.eu/reviews/withkynam-vibecode-pro-max-kit/) | withkynam/vibecode-pro-max-kit | Coding | 82 | STEADY |
| [`xiangyue-zhang-auto-deep-researcher-24x7`](https://hlido.eu/reviews/xiangyue-zhang-auto-deep-researcher-24x7/) | Xiangyue-Zhang/auto-deep-researcher-24x7 | Research | 50 | FADING |
| [`windy3f3f3f3f-claude-code-from-scratch`](https://hlido.eu/reviews/windy3f3f3f3f-claude-code-from-scratch/) | Windy3f3f3f3f/claude-code-from-scratch | Coding | 75 | STEADY |
| [`yv17labs-ghostdesk`](https://hlido.eu/reviews/yv17labs-ghostdesk/) | YV17labs/GhostDesk | Workflow & Automation | 80 | STEADY |
| [`tt-a1i-hive`](https://hlido.eu/reviews/tt-a1i-hive/) | tt-a1i/hive | Coding | 50 | FADING |
| [`havingautism-codemini-cli`](https://hlido.eu/reviews/havingautism-codemini-cli/) | havingautism/Codemini-CLI | Coding | 80 | STEADY |
| [`zjunlp-sciatlas`](https://hlido.eu/reviews/zjunlp-sciatlas/) | zjunlp/SciAtlas | Research | 50 | FADING |
| [`skalesapp-skales`](https://hlido.eu/reviews/skalesapp-skales/) | skalesapp/skales | Coding | 50 | FADING |
| [`zhulinsen-daily-stock-analysis`](https://hlido.eu/reviews/zhulinsen-daily-stock-analysis/) | ZhuLinsen/daily_stock_analysis | Marketing & Content | 75 | STEADY |
| [`google-adk-python`](https://hlido.eu/reviews/google-adk-python/) | google/adk-python | Coding | 50 | FADING |
| [`pingcap-tidb`](https://hlido.eu/reviews/pingcap-tidb/) | pingcap/tidb | Infrastructure | 50 | FADING |
| [`claudiodrews-memory-os`](https://hlido.eu/reviews/claudiodrews-memory-os/) | ClaudioDrews/memory-os | Infrastructure | 73 | STEADY |
| [`elizaos-eliza`](https://hlido.eu/reviews/elizaos-eliza/) | elizaOS/eliza | AI Agent | 50 | FADING |
| [`tencent-weknora`](https://hlido.eu/reviews/tencent-weknora/) | Tencent/WeKnora | AI Agent | 50 | FADING |
| [`flyteorg-flyte`](https://hlido.eu/reviews/flyteorg-flyte/) | flyteorg/flyte | Workflow & Automation | 50 | FADING |
| [`strands-agents-harness-sdk`](https://hlido.eu/reviews/strands-agents-harness-sdk/) | strands-agents/harness-sdk | Coding | 50 | FADING |
| [`the-open-agent-openagent`](https://hlido.eu/reviews/the-open-agent-openagent/) | the-open-agent/openagent | Customer Experience | 50 | FADING |
| [`grab-cursor-talk-to-figma-mcp`](https://hlido.eu/reviews/grab-cursor-talk-to-figma-mcp/) | grab/cursor-talk-to-figma-mcp | Image & Design | 50 | FADING |
| [`crestalnetwork-intentkit`](https://hlido.eu/reviews/crestalnetwork-intentkit/) | crestalnetwork/intentkit | Infrastructure | 50 | FADING |
| [`promptfoo-promptfoo`](https://hlido.eu/reviews/promptfoo-promptfoo/) | promptfoo/promptfoo | AI Agent | 50 | FADING |
| [`ruc-datalab-deepanalyze`](https://hlido.eu/reviews/ruc-datalab-deepanalyze/) | ruc-datalab/DeepAnalyze | AI Agent | 50 | FADING |
| [`can1357-oh-my-pi`](https://hlido.eu/reviews/can1357-oh-my-pi/) | can1357/oh-my-pi | AI Agent | 50 | FADING |
| [`narcooo-inkos`](https://hlido.eu/reviews/narcooo-inkos/) | Narcooo/inkos | AI Agent | 80 | STEADY |
| [`ufomiao-zcf`](https://hlido.eu/reviews/ufomiao-zcf/) | UfoMiao/zcf | Coding | 50 | FADING |
| [`geekjourneyx-md2wechat-skill`](https://hlido.eu/reviews/geekjourneyx-md2wechat-skill/) | geekjourneyx/md2wechat-skill | Chat & Companion | 50 | FADING |
| [`commandcodeai-command-code`](https://hlido.eu/reviews/commandcodeai-command-code/) | CommandCodeAI/command-code | Coding | 50 | FADING |
| [`covibes-zeroshot`](https://hlido.eu/reviews/covibes-zeroshot/) | covibes/zeroshot | Coding | 50 | FADING |
| [`can4hou6joeng4-boss-agent-cli`](https://hlido.eu/reviews/can4hou6joeng4-boss-agent-cli/) | can4hou6joeng4/boss-agent-cli | AI Agent | 50 | FADING |
| [`cloakhq-cloakbrowser`](https://hlido.eu/reviews/cloakhq-cloakbrowser/) | CloakHQ/CloakBrowser | AI Agent | 50 | FADING |
| [`getmaxun-maxun`](https://hlido.eu/reviews/getmaxun-maxun/) | getmaxun/maxun | Coding | 50 | FADING |
| [`pinchtab-pinchtab`](https://hlido.eu/reviews/pinchtab-pinchtab/) | pinchtab/pinchtab | Infrastructure | 82 | STEADY |
| [`h4ckf0r0day-obscura`](https://hlido.eu/reviews/h4ckf0r0day-obscura/) | h4ckf0r0day/obscura | AI Agent | 50 | FADING |
| [`clawd-bot`](https://hlido.eu/reviews/clawd-bot/) | clawd-bot | AI Agent | 50 | FADING |
| [`ioni`](https://hlido.eu/reviews/ioni/) | ioni | AI Agent | 50 | FADING |
| [`muno-work`](https://hlido.eu/reviews/muno-work/) | muno-work | AI Agent | 50 | FADING |
| [`paseru-sinew`](https://hlido.eu/reviews/paseru-sinew/) | Paseru/sinew | Coding | 50 | FADING |
| [`constellation-engine-constellation-engine`](https://hlido.eu/reviews/constellation-engine-constellation-engine/) | CONSTELLATION-ENGINE/constellation-engine | AI Agent | 50 | FADING |
| [`denissergeevitch-agents-best-practices`](https://hlido.eu/reviews/denissergeevitch-agents-best-practices/) | DenisSergeevitch/agents-best-practices | Frameworks & Eval | 82 | STEADY |
| [`zhitongblog-solomd`](https://hlido.eu/reviews/zhitongblog-solomd/) | zhitongblog/solomd | Productivity | 82 | STEADY |
| [`ryjoxtechnologies-octopoda-os`](https://hlido.eu/reviews/ryjoxtechnologies-octopoda-os/) | RyjoxTechnologies/Octopoda-OS | AI Agent | 50 | FADING |
| [`iamcorey-kooky`](https://hlido.eu/reviews/iamcorey-kooky/) | iAmCorey/kooky | Coding | 82 | STEADY |
| [`agentforce314-clawcodex`](https://hlido.eu/reviews/agentforce314-clawcodex/) | agentforce314/clawcodex | Coding | 50 | FADING |
| [`steel-dev-steel-browser`](https://hlido.eu/reviews/steel-dev-steel-browser/) | steel-dev/steel-browser | Coding | 50 | FADING |
| [`autoscrape-labs-pydoll`](https://hlido.eu/reviews/autoscrape-labs-pydoll/) | autoscrape-labs/pydoll | Workflow & Automation | 50 | FADING |
| [`jo-inc-camofox-browser`](https://hlido.eu/reviews/jo-inc-camofox-browser/) | jo-inc/camofox-browser | Infrastructure | 82 | STEADY |
| [`siyuan-note-siyuan`](https://hlido.eu/reviews/siyuan-note-siyuan/) | siyuan-note/siyuan | Productivity | 50 | FADING |
| [`browser-use-workflow-use`](https://hlido.eu/reviews/browser-use-workflow-use/) | browser-use/workflow-use | Workflow & Automation | 50 | FADING |
| [`fellouai-eko`](https://hlido.eu/reviews/fellouai-eko/) | FellouAI/eko | Workflow & Automation | 50 | FADING |
| [`cellium-project-cellium-agent`](https://hlido.eu/reviews/cellium-project-cellium-agent/) | Cellium-Project/Cellium-Agent | AI Agent | 50 | FADING |
| [`longyunfeigu-learn-hermes-agent`](https://hlido.eu/reviews/longyunfeigu-learn-hermes-agent/) | longyunfeigu/learn-hermes-agent | Frameworks & Eval | 82 | STEADY |
| [`ekkolearnai-hermes-studio`](https://hlido.eu/reviews/ekkolearnai-hermes-studio/) | Hermes Studio | Chat & Companion | 74 | — |
| [`worldwonderer-oh-story-claudecode`](https://hlido.eu/reviews/worldwonderer-oh-story-claudecode/) | oh-story-claudecode | Marketing & Content | 63 | — |
| [`playwright-community-playwright-go`](https://hlido.eu/reviews/playwright-community-playwright-go/) | playwright-community/playwright-go | Workflow & Automation | 50 | FADING |
| [`oshayr-llm-wiki`](https://hlido.eu/reviews/oshayr-llm-wiki/) | Oshayr/LLM-Wiki | MCP Server | 82 | STEADY |
| [`raphaelmansuy-edgecrab`](https://hlido.eu/reviews/raphaelmansuy-edgecrab/) | raphaelmansuy/edgecrab | Coding | 50 | FADING |
| [`amap-ml-skillclaw`](https://hlido.eu/reviews/amap-ml-skillclaw/) | SkillClaw | Frameworks & Eval | 70 | — |
| [`sandydasari-openacme`](https://hlido.eu/reviews/sandydasari-openacme/) | OpenAcme | Frameworks & Eval | 61 | — |
| [`yantrikos-yantrikdb-hermes-plugin`](https://hlido.eu/reviews/yantrikos-yantrikdb-hermes-plugin/) | YantrikDB Hermes Plugin | Infrastructure | 57 | — |
| [`windy3f3f3f3f-how-claude-code-works`](https://hlido.eu/reviews/windy3f3f3f3f-how-claude-code-works/) | Windy3f3f3f3f/how-claude-code-works | Coding | 50 | FADING |
| [`skwallace36-pepper`](https://hlido.eu/reviews/skwallace36-pepper/) | skwallace36/Pepper | MCP Server | 82 | STEADY |
| [`walkinglabs-awesome-harness-engineering`](https://hlido.eu/reviews/walkinglabs-awesome-harness-engineering/) | walkinglabs/awesome-harness-engineering | MCP Server | 67 | FADING |
| [`agentplace`](https://hlido.eu/reviews/agentplace/) | agentplace | AI Agent | 50 | FADING |
| [`walkinglabs-hands-on-modern-rl`](https://hlido.eu/reviews/walkinglabs-hands-on-modern-rl/) | walkinglabs/hands-on-modern-rl | AI Agent | 50 | FADING |
| [`cometchat`](https://hlido.eu/reviews/cometchat/) | cometchat | Chat & Companion | 50 | FADING |
| [`pageon`](https://hlido.eu/reviews/pageon/) | pageon | AI Agent | 50 | FADING |
| [`eugeniughelbur-obsidian-second-brain`](https://hlido.eu/reviews/eugeniughelbur-obsidian-second-brain/) | eugeniughelbur/obsidian-second-brain | Coding | 50 | FADING |
| [`adept`](https://hlido.eu/reviews/adept/) | Adept AI | Productivity | 50 | FADING |
| [`kevrojo-dulus`](https://hlido.eu/reviews/kevrojo-dulus/) | KevRojo/Dulus | Infrastructure | 50 | FADING |
| [`atlassian`](https://hlido.eu/reviews/atlassian/) | Atlassian Rovo | Productivity | 50 | FADING |
| [`dietrichgebert-ponytail`](https://hlido.eu/reviews/dietrichgebert-ponytail/) | DietrichGebert/ponytail | Coding | 50 | FADING |
| [`mybono-ai-orchestrator`](https://hlido.eu/reviews/mybono-ai-orchestrator/) | ai-orchestrator | Frameworks & Eval | 58 | — |
| [`prava-space`](https://hlido.eu/reviews/prava-space/) | Prava | Infrastructure | 67 | — |
| [`stakpak-agent`](https://hlido.eu/reviews/stakpak-agent/) | Stakpak | Infrastructure | 71 | — |
| [`sikamikanikobg-homelab-monitor`](https://hlido.eu/reviews/sikamikanikobg-homelab-monitor/) | SikamikanikoBG/homelab-monitor | AI Agent | 50 | FADING |
| [`omnigent-ai-omnigent`](https://hlido.eu/reviews/omnigent-ai-omnigent/) | omnigent-ai/omnigent | Coding | 50 | FADING |
| [`google-antigravity-antigravity-sdk-python`](https://hlido.eu/reviews/google-antigravity-antigravity-sdk-python/) | google-antigravity/antigravity-sdk-python | AI Agent | 50 | FADING |
| [`voltagent`](https://hlido.eu/reviews/voltagent/) | VoltAgent | Frameworks & Eval | 76 | — |
| [`zeroclaw-labs-zeroclaw`](https://hlido.eu/reviews/zeroclaw-labs-zeroclaw/) | ZeroClaw | Infrastructure | 79 | — |
| [`itsinseong-value-for-fable`](https://hlido.eu/reviews/itsinseong-value-for-fable/) | itsinseong/value-for-fable | Coding | 67 | FADING |
| [`scheidydude-codeindex`](https://hlido.eu/reviews/scheidydude-codeindex/) | scheidydude/codeindex | Coding | 82 | STEADY |
| [`modelstudioai-cli`](https://hlido.eu/reviews/modelstudioai-cli/) | modelstudioai/cli | Workflow & Automation | 50 | FADING |
| [`freepeak-leankg`](https://hlido.eu/reviews/freepeak-leankg/) | FreePeak/LeanKG | AI Agent | 50 | FADING |
| [`volcengine-searchcli`](https://hlido.eu/reviews/volcengine-searchcli/) | volcengine/SearchCLI | Frameworks & Eval | 82 | STEADY |
| [`utopai-research-pai-pro`](https://hlido.eu/reviews/utopai-research-pai-pro/) | Utopai-Research/pai-pro | Research | 67 | FADING |
| [`getcrew44-crew44`](https://hlido.eu/reviews/getcrew44-crew44/) | getcrew44/crew44 | AI Agent | 50 | FADING |
| [`the-open-engine-zeroshot`](https://hlido.eu/reviews/the-open-engine-zeroshot/) | the-open-engine/zeroshot | Coding | 50 | FADING |
| [`decolua-9remote`](https://hlido.eu/reviews/decolua-9remote/) | decolua/9remote | Coding | 50 | FADING |
| [`ykdojo-claude-code-tips`](https://hlido.eu/reviews/ykdojo-claude-code-tips/) | ykdojo/claude-code-tips | MCP Server | 67 | FADING |
| [`montferret-ferret`](https://hlido.eu/reviews/montferret-ferret/) | MontFerret/ferret | Workflow & Automation | 50 | FADING |
| [`juanjuandog-finsight-ai`](https://hlido.eu/reviews/juanjuandog-finsight-ai/) | juanjuandog/FinSight-AI | Research | 82 | STEADY |
| [`open-multi-agent-open-multi-agent`](https://hlido.eu/reviews/open-multi-agent-open-multi-agent/) | open-multi-agent/open-multi-agent | Workflow & Automation | 50 | FADING |
| [`mvanhorn-cli-printing-press`](https://hlido.eu/reviews/mvanhorn-cli-printing-press/) | mvanhorn/cli-printing-press | Infrastructure | 82 | STEADY |
| [`juliusbrussee-cavemem`](https://hlido.eu/reviews/juliusbrussee-cavemem/) | JuliusBrussee/cavemem | AI Agent | 50 | FADING |
| [`thedaviddias-front-end-checklist`](https://hlido.eu/reviews/thedaviddias-front-end-checklist/) | thedaviddias/Front-End-Checklist | Coding | 50 | FADING |
| [`cartesia`](https://hlido.eu/reviews/cartesia/) | Cartesia | Voice | 50 | FADING |
| [`imbue`](https://hlido.eu/reviews/imbue/) | Imbue | Productivity | 50 | FADING |
| [`lakera`](https://hlido.eu/reviews/lakera/) | Lakera | Other | 50 | FADING |
| [`jnmetacode-agency-orchestrator`](https://hlido.eu/reviews/jnmetacode-agency-orchestrator/) | jnMetaCode/agency-orchestrator | Coding | 50 | FADING |
| [`e2b`](https://hlido.eu/reviews/e2b/) | E2B Sandboxes | DevOps | 50 | FADING |
| [`letta`](https://hlido.eu/reviews/letta/) | Letta | Frameworks & Eval | 50 | FADING |
| [`lumalabs`](https://hlido.eu/reviews/lumalabs/) | Luma (Dream Machine) | Image & Design | 50 | FADING |
| [`kaelio-ktx`](https://hlido.eu/reviews/kaelio-ktx/) | Kaelio/ktx | Coding | 50 | FADING |
| [`shenmintao-marginalia`](https://hlido.eu/reviews/shenmintao-marginalia/) | shenmintao/marginalia | Productivity | 82 | STEADY |
| [`lukresxd-claw-skeleton`](https://hlido.eu/reviews/lukresxd-claw-skeleton/) | LuKresXD/claw-skeleton | Coding | 82 | STEADY |
| [`nudgebee-nudgebee`](https://hlido.eu/reviews/nudgebee-nudgebee/) | nudgebee/nudgebee | Workflow & Automation | 50 | FADING |
| [`aws-devtools-labs-aws-blocks`](https://hlido.eu/reviews/aws-devtools-labs-aws-blocks/) | aws-devtools-labs/aws-blocks | Coding | 82 | STEADY |
| [`oritera-cairn`](https://hlido.eu/reviews/oritera-cairn/) | oritera/Cairn | AI Agent | 82 | STEADY |
| [`kilo-org-kilocode`](https://hlido.eu/reviews/kilo-org-kilocode/) | kilo-org-kilocode | Coding | 50 | FADING |
| [`prismer-ai-prismercloud`](https://hlido.eu/reviews/prismer-ai-prismercloud/) | Prismer-AI/PrismerCloud | Infrastructure | 85 | STEADY |
| [`marqo`](https://hlido.eu/reviews/marqo/) | Marqo | Other | 75 | STEADY |
| [`copy`](https://hlido.eu/reviews/copy/) | Copy.ai | Marketing & Content | 74 | — |
| [`lindy`](https://hlido.eu/reviews/lindy/) | Lindy | Productivity | 73 | — |
| [`supertrained-rhumb`](https://hlido.eu/reviews/supertrained-rhumb/) | supertrained/rhumb | AI Agent | 50 | FADING |
| [`scotia1973-bot-api-hub`](https://hlido.eu/reviews/scotia1973-bot-api-hub/) | scotia1973-bot/api-hub | AI Agent | 50 | FADING |
| [`sitbon-magg`](https://hlido.eu/reviews/sitbon-magg/) | sitbon/magg | AI Agent | 50 | FADING |
| [`sf1nx-x402station-mcp`](https://hlido.eu/reviews/sf1nx-x402station-mcp/) | sF1nX/x402station-mcp | AI Agent | 50 | FADING |
| [`smart-mcp-proxy-mcpproxy-go`](https://hlido.eu/reviews/smart-mcp-proxy-mcpproxy-go/) | smart-mcp-proxy/mcpproxy-go | Coding | 50 | FADING |
| [`sonnyflylock-voxie-ai-directory-mcp`](https://hlido.eu/reviews/sonnyflylock-voxie-ai-directory-mcp/) | sonnyflylock/voxie-ai-directory-mcp | MCP Server | 60 | FADING |
| [`surescaleai-openai-gpt-image-mcp`](https://hlido.eu/reviews/surescaleai-openai-gpt-image-mcp/) | SureScaleAI/openai-gpt-image-mcp | MCP Server | 53 | FADING |
| [`veriteknik-pluggedin-mcp-proxy`](https://hlido.eu/reviews/veriteknik-pluggedin-mcp-proxy/) | VeriTeknik/pluggedin-mcp-proxy | MCP Server | 82 | STEADY |
| [`tigranbs-mcgravity`](https://hlido.eu/reviews/tigranbs-mcgravity/) | tigranbs/mcgravity | AI Agent | 73 | STEADY |
| [`viperjuice-mcp-gateway`](https://hlido.eu/reviews/viperjuice-mcp-gateway/) | ViperJuice/mcp-gateway | MCP Server | 82 | STEADY |
| [`waystation-ai-mcp`](https://hlido.eu/reviews/waystation-ai-mcp/) | waystation-ai/mcp | AI Agent | 50 | FADING |
| [`whiteknightonhorse-apibase`](https://hlido.eu/reviews/whiteknightonhorse-apibase/) | whiteknightonhorse/APIbase | Infrastructure | 50 | FADING |
| [`x402-index-x402search-mcp`](https://hlido.eu/reviews/x402-index-x402search-mcp/) | x402-index/x402search-mcp | MCP Server | 67 | FADING |
| [`ikoskela-wisepanel-mcp`](https://hlido.eu/reviews/ikoskela-wisepanel-mcp/) | ikoskela/wisepanel-mcp | MCP Server | 82 | STEADY |
| [`swarmwage-swarmwage`](https://hlido.eu/reviews/swarmwage-swarmwage/) | Swarmwage/swarmwage | AI Agent | 50 | FADING |
| [`activepieces-activepieces`](https://hlido.eu/reviews/activepieces-activepieces/) | Activepieces | Workflow & Automation | 76 | — |
| [`askhapax`](https://hlido.eu/reviews/askhapax/) | askhapax | AI Agent | 50 | FADING |
| [`2noise-chattts`](https://hlido.eu/reviews/2noise-chattts/) | 2noise/ChatTTS | Voice | 50 | FADING |
| [`acedatacloud-fluxmcp`](https://hlido.eu/reviews/acedatacloud-fluxmcp/) | AceDataCloud/FluxMCP | MCP Server | 82 | — |
| [`ahujasid-blender-mcp`](https://hlido.eu/reviews/ahujasid-blender-mcp/) | Blender MCP | Image & Design | 82 | — |
| [`airjelly`](https://hlido.eu/reviews/airjelly/) | AirJelly | Productivity | 70 | — |
| [`asmith26-jupytercad-mcp`](https://hlido.eu/reviews/asmith26-jupytercad-mcp/) | jupytercad-mcp | Frameworks & Eval | 66 | — |
| [`run-llama-liteparse`](https://hlido.eu/reviews/run-llama-liteparse/) | LiteParse | Infrastructure | 85 | — |
| [`atlas-new`](https://hlido.eu/reviews/atlas-new/) | Atlas | Specialized verticals | 71 | — |
| [`block-goose`](https://hlido.eu/reviews/block-goose/) | goose | Coding | 84 | — |
| [`epsilla`](https://hlido.eu/reviews/epsilla/) | Epsilla | Frameworks & Eval | 70 | — |
| [`workflowmachine`](https://hlido.eu/reviews/workflowmachine/) | Workflow Machine | Workflow & Automation | 72 | — |
| [`forgemeshlabs-coinopai-mcp`](https://hlido.eu/reviews/forgemeshlabs-coinopai-mcp/) | Kronos (CoinOpAI) | Specialized verticals | 71 | — |
| [`1mcp-app-agent`](https://hlido.eu/reviews/1mcp-app-agent/) | 1MCP Agent | Infrastructure | 74 | — |
| [`mcpqueen-mcpqueen`](https://hlido.eu/reviews/mcpqueen-mcpqueen/) | MCP Queen | Frameworks & Eval | 76 | — |
| [`aganium-agenium`](https://hlido.eu/reviews/aganium-agenium/) | Agenium | Productivity | 58 | — |
| [`agentbodegastore-agentbodega`](https://hlido.eu/reviews/agentbodegastore-agentbodega/) | AgentBodega | Infrastructure | 66 | — |
| [`elisymlabs-elisym`](https://hlido.eu/reviews/elisymlabs-elisym/) | Elisym | Infrastructure | 55 | — |
| [`alexar76-aimarket-plugins`](https://hlido.eu/reviews/alexar76-aimarket-plugins/) | AICOM (AIMarket) | Infrastructure | 60 | — |
| [`rhein1-agoragentic-integrations`](https://hlido.eu/reviews/rhein1-agoragentic-integrations/) | Agoragentic Integrations | Infrastructure | 68 | — |
| [`avotsai-avots-mcp`](https://hlido.eu/reviews/avotsai-avots-mcp/) | Avots MCP | Infrastructure | 72 | — |
| [`data-everything-mcp-server-templates`](https://hlido.eu/reviews/data-everything-mcp-server-templates/) | MCP Server Templates | Infrastructure | 48 | — |
| [`depwire-depwire`](https://hlido.eu/reviews/depwire-depwire/) | Depwire | Coding | 79 | — |
| [`carlosahumada89-govrider-mcp-server`](https://hlido.eu/reviews/carlosahumada89-govrider-mcp-server/) | Govrider | Specialized verticals | 44 | — |
| [`jabbawocky-proposalcraft`](https://hlido.eu/reviews/jabbawocky-proposalcraft/) | ProposalCraft | Productivity | 68 | — |
| [`jovancoding-network-ai`](https://hlido.eu/reviews/jovancoding-network-ai/) | Network-AI | Frameworks & Eval | 76 | — |
| [`julien040-anyquery`](https://hlido.eu/reviews/julien040-anyquery/) | Anyquery | Infrastructure | 78 | — |
| [`juspay-neurolink`](https://hlido.eu/reviews/juspay-neurolink/) | NeuroLink | Infrastructure | 60 | — |
| [`google-gemini-gemini-cli`](https://hlido.eu/reviews/google-gemini-gemini-cli/) | Gemini CLI | Coding | 76 | — |
| [`clanker-records-crompton-network`](https://hlido.eu/reviews/clanker-records-crompton-network/) | C.W.A. (Crompton Network) | AI Agent | 45 | — |
| [`forcedreamai-forcedream-mcp`](https://hlido.eu/reviews/forcedreamai-forcedream-mcp/) | ForceDream | Infrastructure | 50 | — |
| [`humanforai-humanforai-mcp`](https://hlido.eu/reviews/humanforai-humanforai-mcp/) | Human For AI | Specialized verticals | 66 | — |
| [`opentabs-dev-opentabs`](https://hlido.eu/reviews/opentabs-dev-opentabs/) | OpenTabs | Infrastructure | 64 | — |
| [`pantani-ableton-mind`](https://hlido.eu/reviews/pantani-ableton-mind/) | ableton-mind | Specialized verticals | 72 | — |
| [`pantani-tdmcp`](https://hlido.eu/reviews/pantani-tdmcp/) | tdmcp | Specialized verticals | 70 | — |
| [`portel-dev-ncp`](https://hlido.eu/reviews/portel-dev-ncp/) | NCP (Natural Context Provider) | Infrastructure | 71 | — |
| [`glama-ai-tool-definition-quality-score`](https://hlido.eu/reviews/glama-ai-tool-definition-quality-score/) | Tool Definition Quality Score (TDQS) | Frameworks & Eval | 73 | — |
| [`quokkapix-quokkapix-mcp`](https://hlido.eu/reviews/quokkapix-quokkapix-mcp/) | QuokkaPix MCP Runner | Image & Design | 74 | — |
| [`singhpratech-crimson-crab-mcp-template`](https://hlido.eu/reviews/singhpratech-crimson-crab-mcp-template/) | crimson-crab | Frameworks & Eval | 76 | — |
| [`thebrierfox-the-stall`](https://hlido.eu/reviews/thebrierfox-the-stall/) | The Stall | Infrastructure | 58 | — |
| [`tsouth89-toolport`](https://hlido.eu/reviews/tsouth89-toolport/) | Toolport | Infrastructure | 84 | — |
| [`cafferychen777-chatspatial`](https://hlido.eu/reviews/cafferychen777-chatspatial/) | ChatSpatial | Specialized verticals | 72 | — |
| [`kentucky-ai-opentakeoff`](https://hlido.eu/reviews/kentucky-ai-opentakeoff/) | OpenTakeoff | Specialized verticals | 70 | — |
| [`bobaba99-motionlint`](https://hlido.eu/reviews/bobaba99-motionlint/) | MotionLint | Frameworks & Eval | 80 | — |
| [`genomoncology-biomcp`](https://hlido.eu/reviews/genomoncology-biomcp/) | BioMCP | Specialized verticals | 82 | — |
| [`raveenb-fal-mcp-server`](https://hlido.eu/reviews/raveenb-fal-mcp-server/) | Fal MCP Server | Image & Design | 62 | — |
| [`dnaerys-onekgpd-mcp`](https://hlido.eu/reviews/dnaerys-onekgpd-mcp/) | Dnaerys 1000 Genomes MCP | Specialized verticals | 63 | — |
| [`healthchainai-healthchain`](https://hlido.eu/reviews/healthchainai-healthchain/) | HealthChain | Specialized verticals | 66 | — |
| [`mymedi-ai-mymedi-ai-mcp-server`](https://hlido.eu/reviews/mymedi-ai-mymedi-ai-mcp-server/) | MyMedi-AI Bot Marketplace | Specialized verticals | 65 | — |
| [`rdanieli-tentra-mcp`](https://hlido.eu/reviews/rdanieli-tentra-mcp/) | Tentra | Infrastructure | 68 | — |
| [`tatsuju-opdstar-nhi-mcp`](https://hlido.eu/reviews/tatsuju-opdstar-nhi-mcp/) | OPDSTAR | Specialized verticals | 58 | — |
| [`uxloom-dev-uxloom`](https://hlido.eu/reviews/uxloom-dev-uxloom/) | UXLoom | Frameworks & Eval | 71 | — |
| [`segentic-lab-periscope-mcp`](https://hlido.eu/reviews/segentic-lab-periscope-mcp/) | Periscope MCP (Segentic Lab) | Frameworks & Eval | 61 | — |
| [`john-broadway-proximo`](https://hlido.eu/reviews/john-broadway-proximo/) | Proximo | Infrastructure | 76 | — |
| [`johnneerdael-netskope-mcp`](https://hlido.eu/reviews/johnneerdael-netskope-mcp/) | Netskope NPA MCP | Infrastructure | 80 | — |
| [`swimmwatch-cloakbrowser-mcp`](https://hlido.eu/reviews/swimmwatch-cloakbrowser-mcp/) | CloakBrowser MCP | Frameworks & Eval | 77 | — |
| [`vincentvella-devloop`](https://hlido.eu/reviews/vincentvella-devloop/) | Devloop | Coding | 79 | — |
| [`nwiizo-tfmcp`](https://hlido.eu/reviews/nwiizo-tfmcp/) | tfmcp | Infrastructure | 64 | — |
| [`acedatacloud-seedreammcp`](https://hlido.eu/reviews/acedatacloud-seedreammcp/) | AceDataCloud/SeedreamMCP | MCP Server | 82 | — |
| [`agentscope-ai-agentscope`](https://hlido.eu/reviews/agentscope-ai-agentscope/) | AgentScope | AI Agent | 70 | — |
| [`aliafsahnoudeh-shahnameh-mcp-server`](https://hlido.eu/reviews/aliafsahnoudeh-shahnameh-mcp-server/) | aliafsahnoudeh/shahnameh-mcp-server | MCP Server | 60 | — |
| [`alikarami-mikromcp`](https://hlido.eu/reviews/alikarami-mikromcp/) | MikroMCP | Infrastructure | 79 | — |
| [`attalla1-photopea-mcp-server`](https://hlido.eu/reviews/attalla1-photopea-mcp-server/) | attalla1/photopea-mcp-server | Image & Design | 80 | — |
| [`awslabs-mcp`](https://hlido.eu/reviews/awslabs-mcp/) | Open Source MCP Servers for AWS | Infrastructure | 83 | — |
| [`bluesprince-thiri-mcp`](https://hlido.eu/reviews/bluesprince-thiri-mcp/) | BluesPrince/thiri-mcp | MCP Server | 80 | — |
| [`chaandannn-finopsmcp`](https://hlido.eu/reviews/chaandannn-finopsmcp/) | nable | Infrastructure | 74 | — |
| [`eat-pray-ai-yutu`](https://hlido.eu/reviews/eat-pray-ai-yutu/) | yutu | Marketing & Content | 71 | — |
| [`ertad-family-liquid`](https://hlido.eu/reviews/ertad-family-liquid/) | ertad-family/liquid | MCP Server | 80 | — |
| [`executeautomation-mcp-playwright`](https://hlido.eu/reviews/executeautomation-mcp-playwright/) | Playwright MCP Server (ExecuteAutomation) | Frameworks & Eval | 58 | — |
| [`feedthrough-feedthrough`](https://hlido.eu/reviews/feedthrough-feedthrough/) | Feedthrough | Coding | 78 | — |
| [`gregario-astronomy-oracle`](https://hlido.eu/reviews/gregario-astronomy-oracle/) | gregario/astronomy-oracle | MCP Server | 82 | — |
| [`hshintelligence-agent-scrape`](https://hlido.eu/reviews/hshintelligence-agent-scrape/) | AgentScrape | Infrastructure | 69 | — |
| [`junipr-labs-mcp-server`](https://hlido.eu/reviews/junipr-labs-mcp-server/) | Junipr MCP Server | Workflow & Automation | 41 | — |
| [`leo-lilinxiao-codex-autoresearch`](https://hlido.eu/reviews/leo-lilinxiao-codex-autoresearch/) | leo-lilinxiao/codex-autoresearch | Developer Tool | 82 | — |
| [`mathiaspaulenko-wavexis-mcp`](https://hlido.eu/reviews/mathiaspaulenko-wavexis-mcp/) | WaveXisMCP | Infrastructure | 81 | — |
| [`tc-rebillion`](https://hlido.eu/reviews/tc-rebillion/) | AI Transaction Coordination for Real Estate | ReBillion | Workflow & Automation | 90 | — |
| [`youngbryan97-aura`](https://hlido.eu/reviews/youngbryan97-aura/) | youngbryan97/aura | Developer Tool | 80 | — |
| [`tencentcloudbase-cloudbase-ai-toolkit`](https://hlido.eu/reviews/tencentcloudbase-cloudbase-ai-toolkit/) | CloudBase AI ToolKit | Infrastructure | 82 | — |
| [`txn2-kubefwd`](https://hlido.eu/reviews/txn2-kubefwd/) | kubefwd | Infrastructure | 80 | — |
| [`agent-blueprint-mcp-server`](https://hlido.eu/reviews/agent-blueprint-mcp-server/) | Agent Blueprint | Coding | 64 | — |
| [`avansaber-tailtest-cline`](https://hlido.eu/reviews/avansaber-tailtest-cline/) | tailtest | Frameworks & Eval | 77 | — |
| [`onecli-onecli`](https://hlido.eu/reviews/onecli-onecli/) | OneCLI | Infrastructure | 76 | — |
| [`orite`](https://hlido.eu/reviews/orite/) | Orite | Infrastructure | 52 | — |
| [`phinq`](https://hlido.eu/reviews/phinq/) | Phinq | Infrastructure | 72 | — |
| [`sinameraji-hotcell`](https://hlido.eu/reviews/sinameraji-hotcell/) | hotcell | Infrastructure | 80 | — |
| [`sshahzaiib-agy-bridge`](https://hlido.eu/reviews/sshahzaiib-agy-bridge/) | agy-bridge | Coding | 66 | — |
| [`yepcode-mcp-server-js`](https://hlido.eu/reviews/yepcode-mcp-server-js/) | YepCode MCP Server | Infrastructure | 73 | — |
| [`yoanwai-agent-manager`](https://hlido.eu/reviews/yoanwai-agent-manager/) | Agent Manager | Coding | 73 | — |
| [`irskep-persistproc`](https://hlido.eu/reviews/irskep-persistproc/) | persistproc | Infrastructure | 64 | — |
| [`jrswab-axe`](https://hlido.eu/reviews/jrswab-axe/) | Axe | Frameworks & Eval | 70 | — |
| [`kubit`](https://hlido.eu/reviews/kubit/) | Kubit | Frameworks & Eval | 74 | — |
| [`r33drichards-mcp-js`](https://hlido.eu/reviews/r33drichards-mcp-js/) | mcp-v8 | Infrastructure | 80 | — |
| [`lacs-project-sysknife`](https://hlido.eu/reviews/lacs-project-sysknife/) | SysKnife | Infrastructure | 81 | — |
| [`oraios-serena`](https://hlido.eu/reviews/oraios-serena/) | Serena | Coding | 84 | — |
| [`rtrvr`](https://hlido.eu/reviews/rtrvr/) | Rover | Customer Experience | 66 | — |
| [`shashankss1205-codegraphcontext`](https://hlido.eu/reviews/shashankss1205-codegraphcontext/) | CodeGraphContext | Coding | 76 | — |
| [`squadcue`](https://hlido.eu/reviews/squadcue/) | SquadCue | Workflow & Automation | 73 | — |
| [`twill`](https://hlido.eu/reviews/twill/) | Twill | Coding | 74 | — |
| [`wende-cicada`](https://hlido.eu/reviews/wende-cicada/) | Cicada | Coding | 76 | — |
| [`luisgf-infrabroker`](https://hlido.eu/reviews/luisgf-infrabroker/) | infrabroker | Infrastructure | 74 | — |
| [`ksterx-srunx`](https://hlido.eu/reviews/ksterx-srunx/) | srunx | Infrastructure | 72 | — |
| [`vizard`](https://hlido.eu/reviews/vizard/) | Vizard | Marketing & Content | 74 | — |
| [`whodunnitai`](https://hlido.eu/reviews/whodunnitai/) | WhoDunnitAI | Voice | 60 | — |
| [`yomiracle-trinity-lite`](https://hlido.eu/reviews/yomiracle-trinity-lite/) | Trinity Lite | Workflow & Automation | 73 | — |
| [`soren-achebe-backscroll`](https://hlido.eu/reviews/soren-achebe-backscroll/) | backscroll | Infrastructure | 70 | — |
| [`blinkingbit-oss-execkit`](https://hlido.eu/reviews/blinkingbit-oss-execkit/) | execkit | Infrastructure | 74 | — |
| [`easton-ou-rootpilot-mcp`](https://hlido.eu/reviews/easton-ou-rootpilot-mcp/) | RootPilot | Infrastructure | 71 | — |
| [`anypost-emailmd`](https://hlido.eu/reviews/anypost-emailmd/) | emailmd | Marketing & Content | 72 | — |
| [`automatelab-tech-content-distribution-mcp`](https://hlido.eu/reviews/automatelab-tech-content-distribution-mcp/) | Content Distribution MCP | Marketing & Content | 74 | — |
| [`bababoi-bibilabu-agent-mq`](https://hlido.eu/reviews/bababoi-bibilabu-agent-mq/) | agent-mq | Infrastructure | 58 | — |
| [`ethanqc-feishu-user-plugin`](https://hlido.eu/reviews/ethanqc-feishu-user-plugin/) | feishu-user-plugin | Productivity | 71 | — |
| [`omniwork`](https://hlido.eu/reviews/omniwork/) | Omniwork | Marketing & Content | 69 | — |
| [`cactuscompute`](https://hlido.eu/reviews/cactuscompute/) | Cactus | Infrastructure | 73 | — |
| [`operative-sh-web-eval-agent`](https://hlido.eu/reviews/operative-sh-web-eval-agent/) | Operative (web-eval-agent) | Frameworks & Eval | 72 | — |
| [`imdinu-apple-mail-mcp`](https://hlido.eu/reviews/imdinu-apple-mail-mcp/) | Apple Mail MCP | Productivity | 75 | — |
| [`joinly-ai-joinly`](https://hlido.eu/reviews/joinly-ai-joinly/) | joinly.ai | Productivity | 68 | — |
| [`kushneryk-join-cloud`](https://hlido.eu/reviews/kushneryk-join-cloud/) | Join.cloud | Infrastructure | 74 | — |
| [`codewithbullet`](https://hlido.eu/reviews/codewithbullet/) | Bullet | Coding | 73 | — |
| [`fathom`](https://hlido.eu/reviews/fathom/) | Fathom | Productivity | 76 | — |
| [`ztxtxwd-open-feishu-mcp-server`](https://hlido.eu/reviews/ztxtxwd-open-feishu-mcp-server/) | Feishu MCP Server | Infrastructure | 52 | — |
| [`aymericzip-intlayer`](https://hlido.eu/reviews/aymericzip-intlayer/) | Intlayer | Coding | 73 | — |
| [`centralmind-gateway`](https://hlido.eu/reviews/centralmind-gateway/) | CentralMind Gateway | Infrastructure | 74 | — |
| [`clarasdr`](https://hlido.eu/reviews/clarasdr/) | Clara | Customer Experience | 57 | — |
| [`frowningdev-django-orm-lens`](https://hlido.eu/reviews/frowningdev-django-orm-lens/) | Django ORM Lens | Coding | 84 | — |
| [`googleapis-genai-toolbox`](https://hlido.eu/reviews/googleapis-genai-toolbox/) | MCP Toolbox for Databases | Infrastructure | 85 | — |
| [`neo4j-contrib-mcp-neo4j`](https://hlido.eu/reviews/neo4j-contrib-mcp-neo4j/) | Neo4j MCP Integrations | Infrastructure | 74 | — |
| [`rashidazarang-airtable-mcp`](https://hlido.eu/reviews/rashidazarang-airtable-mcp/) | Airtable MCP | Infrastructure | 79 | — |
| [`superhq-ai-superhq`](https://hlido.eu/reviews/superhq-ai-superhq/) | SuperHQ | Coding | 63 | — |
| [`feedoracle`](https://hlido.eu/reviews/feedoracle/) | FeedOracle | Specialized verticals | 80 | — |
| [`clarkchat`](https://hlido.eu/reviews/clarkchat/) | Clark Labs | AI Agent | 66 | — |
| [`roomote`](https://hlido.eu/reviews/roomote/) | Roomote | Coding | 78 | — |
| [`screenpipe-screenpipe`](https://hlido.eu/reviews/screenpipe-screenpipe/) | screenpipe | Productivity | 81 | — |
| [`claude-code`](https://hlido.eu/reviews/claude-code/) | Claude Code | Coding | 91 | — |
| [`supabase-community-supabase-mcp`](https://hlido.eu/reviews/supabase-community-supabase-mcp/) | Supabase MCP Server | Infrastructure | 85 | — |
| [`callstackincubator-agent-device`](https://hlido.eu/reviews/callstackincubator-agent-device/) | agent-device | Coding | 80 | — |
| [`deusdata-codebase-memory-mcp`](https://hlido.eu/reviews/deusdata-codebase-memory-mcp/) | codebase-memory-mcp | Coding | 82 | — |
| [`drhalto-agentmako`](https://hlido.eu/reviews/drhalto-agentmako/) | agentmako | Coding | 74 | — |
| [`ozgurcd-gograph`](https://hlido.eu/reviews/ozgurcd-gograph/) | gograph | Coding | 80 | — |
| [`hyperprobe`](https://hlido.eu/reviews/hyperprobe/) | HyperProbe | Infrastructure | 71 | — |
| [`klaw`](https://hlido.eu/reviews/klaw/) | klaw | Infrastructure | 64 | — |
| [`statewright-statewright`](https://hlido.eu/reviews/statewright-statewright/) | Statewright | Workflow & Automation | 73 | — |
| [`openai-codex`](https://hlido.eu/reviews/openai-codex/) | Codex CLI | Coding | 85 | — |
| [`zw008-vmware-aiops`](https://hlido.eu/reviews/zw008-vmware-aiops/) | vmware-aiops (agent skill) | Infrastructure | 56 | — |
| [`augmnt-augments-mcp-server`](https://hlido.eu/reviews/augmnt-augments-mcp-server/) | Augments | Coding | 73 | — |
| [`automation-ai-labs-mcp-link`](https://hlido.eu/reviews/automation-ai-labs-mcp-link/) | MCP.Link | Workflow & Automation | 72 | — |
| [`bgauryy-octocode-mcp`](https://hlido.eu/reviews/bgauryy-octocode-mcp/) | Octocode | Coding | 82 | — |
| [`cjo4m06-mcp-shrimp-task-manager`](https://hlido.eu/reviews/cjo4m06-mcp-shrimp-task-manager/) | Shrimp Task Manager | Coding | 75 | — |
| [`muvon-octocode`](https://hlido.eu/reviews/muvon-octocode/) | Octocode (muvon) | Coding | 78 | — |
| [`phpcodearcheology-phpcodearcheology`](https://hlido.eu/reviews/phpcodearcheology-phpcodearcheology/) | PhpCodeArcheology | Coding | 77 | — |
| [`glips-figma-context-mcp`](https://hlido.eu/reviews/glips-figma-context-mcp/) | Framelink | Coding | 80 | — |
| [`haris-musa-excel-mcp-server`](https://hlido.eu/reviews/haris-musa-excel-mcp-server/) | Excel MCP Server | Productivity | 74 | — |
| [`hidai25-eval-view`](https://hlido.eu/reviews/hidai25-eval-view/) | EvalView | Frameworks & Eval | 70 | — |
| [`hyperb1iss-droidmind`](https://hlido.eu/reviews/hyperb1iss-droidmind/) | DroidMind | Specialized verticals | 71 | — |
| [`construct-computer`](https://hlido.eu/reviews/construct-computer/) | Construct | Workflow & Automation | 76 | — |
| [`agnost`](https://hlido.eu/reviews/agnost/) | Agnost AI | Frameworks & Eval | 78 | — |
| [`blackwell-systems-agent-lsp`](https://hlido.eu/reviews/blackwell-systems-agent-lsp/) | agent-lsp | Coding | 79 | — |
| [`lpigeon-ros-mcp-server`](https://hlido.eu/reviews/lpigeon-ros-mcp-server/) | RobotMCP | Specialized verticals | 81 | — |
| [`anyframe`](https://hlido.eu/reviews/anyframe/) | AnyFrame | Workflow & Automation | 71 | — |
| [`joinkatalyst`](https://hlido.eu/reviews/joinkatalyst/) | Katalyst | Customer Experience | 73 | — |
| [`axel-build`](https://hlido.eu/reviews/axel-build/) | Axel | Workflow & Automation | 70 | — |
| [`forcedream`](https://hlido.eu/reviews/forcedream/) | ForceDream | Infrastructure | 70 | — |
| [`maritime`](https://hlido.eu/reviews/maritime/) | Maritime | Infrastructure | 75 | — |
| [`proliferate-ai-proliferate`](https://hlido.eu/reviews/proliferate-ai-proliferate/) | Proliferate | Coding | 73 | — |
| [`sbroenne-mcp-server-excel`](https://hlido.eu/reviews/sbroenne-mcp-server-excel/) | Excel MCP Server | Workflow & Automation | 80 | — |
| [`srclight-srclight`](https://hlido.eu/reviews/srclight-srclight/) | Srclight | Coding | 72 | — |
| [`utensils-mcp-nixos`](https://hlido.eu/reviews/utensils-mcp-nixos/) | MCP-NixOS | Infrastructure | 78 | — |
| [`veelenga-claude-mermaid`](https://hlido.eu/reviews/veelenga-claude-mermaid/) | claude-mermaid | Coding | 80 | — |
| [`chronulusai-chronulus-mcp`](https://hlido.eu/reviews/chronulusai-chronulus-mcp/) | Chronulus AI (MCP) | Research | 62 | — |
| [`dograh`](https://hlido.eu/reviews/dograh/) | Dograh | Voice | 76 | — |
| [`childrentime-reactuse`](https://hlido.eu/reviews/childrentime-reactuse/) | ReactUse | Coding | 74 | — |
| [`dataeval-dingo`](https://hlido.eu/reviews/dataeval-dingo/) | Dingo | Frameworks & Eval | 72 | — |
| [`datalayer-jupyter-mcp-server`](https://hlido.eu/reviews/datalayer-jupyter-mcp-server/) | Jupyter MCP Server | Coding | 74 | — |
| [`kdqed-zaturn`](https://hlido.eu/reviews/kdqed-zaturn/) | Zaturn | Research | 58 | — |
| [`vlayer-xyz-vlayer`](https://hlido.eu/reviews/vlayer-xyz-vlayer/) | vlayer | Infrastructure | 70 | — |
| [`splitsense`](https://hlido.eu/reviews/splitsense/) | Splitsense | Marketing & Content | 73 | — |
| [`topview`](https://hlido.eu/reviews/topview/) | Topview | Image & Design | 80 | — |
| [`nteract-semiotic`](https://hlido.eu/reviews/nteract-semiotic/) | Semiotic | Developer Tool | 75 | — |
| [`reflexio`](https://hlido.eu/reviews/reflexio/) | Reflexio | Infrastructure | 78 | — |
| [`doop-design`](https://hlido.eu/reviews/doop-design/) | Doop | Image & Design | 77 | — |
| [`kombai`](https://hlido.eu/reviews/kombai/) | Kombai | Image & Design | 75 | — |
| [`valory-xyz-open-autonomy`](https://hlido.eu/reviews/valory-xyz-open-autonomy/) | Open Autonomy (Olas) | Frameworks & Eval | 73 | — |
| [`vladimir-human-humanizer-ru`](https://hlido.eu/reviews/vladimir-human-humanizer-ru/) | humanizer-ru | Specialized verticals | 66 | — |
| [`get-concord-ai-concord-mcp`](https://hlido.eu/reviews/get-concord-ai-concord-mcp/) | Concord AI | Infrastructure | 70 | — |
| [`modeinspect`](https://hlido.eu/reviews/modeinspect/) | Mode | Image & Design | 76 | — |
| [`ayman3000-naseem-app`](https://hlido.eu/reviews/ayman3000-naseem-app/) | Naseem | Coding | 79 | — |
| [`q00-ouroboros`](https://hlido.eu/reviews/q00-ouroboros/) | Ouroboros | Frameworks & Eval | 74 | — |
| [`gozargah-marzban`](https://hlido.eu/reviews/gozargah-marzban/) | Marzban | Infrastructure | 70 | — |
| [`harden`](https://hlido.eu/reviews/harden/) | Harden | Infrastructure | 85 | — |
| [`theloqua`](https://hlido.eu/reviews/theloqua/) | Loqua | Voice | 72 | — |
| [`gabrielmaialva33-winx-code-agent`](https://hlido.eu/reviews/gabrielmaialva33-winx-code-agent/) | Winx | Coding | 78 | — |
| [`jamesanz-medical-mcp`](https://hlido.eu/reviews/jamesanz-medical-mcp/) | medical-mcp | Specialized verticals | 68 | — |
| [`joaoh82-rustunnel`](https://hlido.eu/reviews/joaoh82-rustunnel/) | rustunnel | Infrastructure | 80 | — |
| [`helloaria`](https://hlido.eu/reviews/helloaria/) | Hello Aria | Productivity | 71 | — |
| [`driven`](https://hlido.eu/reviews/driven/) | Driven | Specialized verticals | 74 | — |
| [`nikolai-vysotskyi-trace-mcp`](https://hlido.eu/reviews/nikolai-vysotskyi-trace-mcp/) | trace-mcp | Coding | 77 | — |
| [`ajitpratap0-gosqlx`](https://hlido.eu/reviews/ajitpratap0-gosqlx/) | GoSQLX | Infrastructure | 75 | — |
| [`kestra-io-mcp-server-python`](https://hlido.eu/reviews/kestra-io-mcp-server-python/) | kestra-io/mcp-server-python | Workflow & Automation | 74 | — |
| [`acedatacloud-mcpnanobanana`](https://hlido.eu/reviews/acedatacloud-mcpnanobanana/) | AceDataCloud MCP Nano Banana | Image & Design | 72 | — |
| [`theguysudo-enzo`](https://hlido.eu/reviews/theguysudo-enzo/) | ENZO | Productivity | 71 | — |
| [`naw103-foremerge`](https://hlido.eu/reviews/naw103-foremerge/) | Foremerge | Coding | 80 | — |
| [`otodock-oto-dock`](https://hlido.eu/reviews/otodock-oto-dock/) | OtoDock | Workflow & Automation | 73 | — |
| [`radix-os`](https://hlido.eu/reviews/radix-os/) | Radix | Coding | 70 | — |
| [`devmate`](https://hlido.eu/reviews/devmate/) | DevMate.AI | Coding | 40 | — |
| [`iris-agent`](https://hlido.eu/reviews/iris-agent/) | Iris | Workflow & Automation | 62 | — |
| [`recurse`](https://hlido.eu/reviews/recurse/) | Recurse | Infrastructure | 73 | — |
| [`sparrow-land`](https://hlido.eu/reviews/sparrow-land/) | Sparrow | Infrastructure | 68 | — |
| [`openappa`](https://hlido.eu/reviews/openappa/) | OpenAPPA | Infrastructure | 64 | — |
| [`rxfilm`](https://hlido.eu/reviews/rxfilm/) | RxFilmStudio | Image & Design | 60 | — |
| [`evermind-ai-raven`](https://hlido.eu/reviews/evermind-ai-raven/) | Raven (EverMind) | Workflow & Automation | 70 | — |
| [`0xsteph-pentest-ai-agents`](https://hlido.eu/reviews/0xsteph-pentest-ai-agents/) | Pentest-AI | Specialized verticals | 81 | — |
| [`phrasee`](https://hlido.eu/reviews/phrasee/) | Jacquard (formerly Phrasee) | Marketing & Content | 70 | — |
| [`wise-vision-mcp-server-ros-2`](https://hlido.eu/reviews/wise-vision-mcp-server-ros-2/) | WiseVision ROS2 MCP | Infrastructure | 80 | — |
| [`graphicle-ai-graphicle`](https://hlido.eu/reviews/graphicle-ai-graphicle/) | Graphicle (KarLex AI) | Coding | 74 | — |
| [`superset`](https://hlido.eu/reviews/superset/) | Superset | Coding | 69 | — |
| [`trytofu`](https://hlido.eu/reviews/trytofu/) | Tofu | Infrastructure | 79 | — |
| [`offrun`](https://hlido.eu/reviews/offrun/) | Offrun | Coding | 78 | — |
| [`agent37`](https://hlido.eu/reviews/agent37/) | Agent 37 | Infrastructure | 80 | — |
| [`traceforce`](https://hlido.eu/reviews/traceforce/) | Traceforce | Specialized verticals | 73 | — |
| [`getviberia`](https://hlido.eu/reviews/getviberia/) | Viberia | Coding | 62 | — |
| [`arena42`](https://hlido.eu/reviews/arena42/) | Arena42 (Agent Arena) | Frameworks & Eval | 73 | — |
| [`clawezy`](https://hlido.eu/reviews/clawezy/) | Clawezy | Infrastructure | 67 | — |
| [`broxi`](https://hlido.eu/reviews/broxi/) | Broxi AI | Workflow & Automation | 63 | — |
| [`openchatcut`](https://hlido.eu/reviews/openchatcut/) | OpenChatCut | Image & Design | 77 | — |
| [`docker-docker-agent`](https://hlido.eu/reviews/docker-docker-agent/) | Docker Agent | Infrastructure | 83 | — |
| [`preset-io-agor`](https://hlido.eu/reviews/preset-io-agor/) | Agor (by Preset) | Workflow & Automation | 76 | — |
| [`agent-reviews`](https://hlido.eu/reviews/agent-reviews/) | agent.reviews | Frameworks & Eval | 71 | — |
| [`pocketty`](https://hlido.eu/reviews/pocketty/) | pocketty | Infrastructure | 74 | — |
| [`openparrot`](https://hlido.eu/reviews/openparrot/) | Parrot | Productivity | 81 | — |
| [`thecraftagents`](https://hlido.eu/reviews/thecraftagents/) | Craft Agents | Workflow & Automation | 79 | — |
| [`lancetta`](https://hlido.eu/reviews/lancetta/) | Lancetta | Productivity | 78 | — |
| [`praex`](https://hlido.eu/reviews/praex/) | Praex | Coding | 73 | — |
| [`navige`](https://hlido.eu/reviews/navige/) | Navige | Infrastructure | 71 | — |

## Files in this mirror

| File | What it contains |
|---|---|
| `review-registry-public.json` | Sanitized index of every published review — slug, name, category, score, tier, summary, review URL, reviewed_at. The single fastest way to load the corpus into your script |
| `scorecards/{slug}.json` | Per-agent structured claim-vs-evidence scorecard. Fields: claim · verdict · evidence quote · source surface (homepage / pricing / docs / cli / api). Same schema for every agent regardless of how it was tested |
| `mcp-server-card.json` | Hlido MCP server advertisement — endpoint, transports, available tools, auth scheme |
| `llms.txt` | LLM-friendly discovery hint (per the proposed [llms.txt](https://llmstxt.org) spec) |
| `llms-full.txt` | Full review corpus rendered as plaintext for AEO / answer-engine ingest |
| `feed.xml` | RSS 2.0 of recently published reviews |
| `sitemap-news.xml` | Google News-style sitemap of last 48h publishes |
| `open-data/manifest.json` | Manifest for the CC-BY-4.0 open data dump on hlido.eu — generated_at, item count, SHA-256, license. The dump itself is at <https://hlido.eu/data/open/hlido-corpus.jsonl> |
| `open-data/LICENSE.md` | CC-BY-4.0 license + citation guidance for the open data dump (more permissive than the HF dataset's CC-BY-NC) |

## Open data dump (CC-BY-4.0)

The full review corpus is published as a single JSONL file under a permissive **CC-BY-4.0** license — academic citation and AI-training-corpus inclusion are explicitly welcome. The dump lives at:

- **Dump:** <https://hlido.eu/data/open/hlido-corpus.jsonl>
- **Manifest:** <https://hlido.eu/data/open/manifest.json>
- **Checksum:** <https://hlido.eu/data/open/hlido-corpus.jsonl.sha256>
- **Landing page + schema:** <https://hlido.eu/data/open/>

Refresh cadence: quarterly. Verify integrity with `sha256sum -c hlido-corpus.jsonl.sha256`.

## How to use this mirror

### Read the corpus

```bash
# Full sanitized index
curl -L https://raw.githubusercontent.com/ankitkapur1992-hlido/hlido-public/main/review-registry-public.json

# A specific scorecard
curl -L https://raw.githubusercontent.com/ankitkapur1992-hlido/hlido-public/main/scorecards/aider.json
```

### Call the MCP server

```bash
# trust_check
curl -X POST https://hlido.eu/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"trust_check","arguments":{"agent_or_url":"aider"}}}'

# find_similar_agents (semantic search via OpenAI embeddings + Cloudflare Vectorize)
curl -X POST https://hlido.eu/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"find_similar_agents","arguments":{"description":"AI coding assistant that edits files in a git repo","top_k":5}}}'
```

### Connect from any MCP-aware client

Drop this into Claude Desktop, Cursor, Cline, Continue, or any MCP-aware app:

```json
{
  "mcpServers": {
    "hlido": {
      "type": "streamable-http",
      "url": "https://hlido.eu/mcp"
    }
  }
}
```

## What's NOT in this repo

We publish results, not the recipe. The following stay private and are intentionally not mirrored here:

- Scoring formula weights and the exact rubric mechanics
- Raw test artifacts (browser sessions, intermediate logs, internal screenshots)
- Pre-publication opinion drafts and dispute correspondence
- Operator credentials, dashboards, and internal automation state

If a vendor wants to dispute a published verdict, the [`report_review_issue`](https://hlido.eu/integrations/#mcp-tools) MCP tool routes that request through our re-test queue with the same rigor as the original review.

## License

Public review summaries and scorecards in this repo: **CC-BY-SA 4.0** — fork, redistribute, build on top, with attribution.

Hlido logo, brand, scoring methodology, and platform code: **All rights reserved**.

## Contact

- Founder: [Ankit Kapur](mailto:ankit@hlido.eu)
- Live site: [hlido.eu](https://hlido.eu)
- Submit an agent for review: [hlido.eu/integrations/#mcp-tools](https://hlido.eu/integrations/#mcp-tools) → `submit_agent` or `request_quick_audit`

---

_This README and the rest of this mirror are auto-regenerated on every publish via [scripts/public-repo-sync.mjs](https://github.com/ankitkapur1992-hlido/hlido-public#) in the upstream Hlido pipeline. Do not edit directly — changes will be overwritten on the next publish._