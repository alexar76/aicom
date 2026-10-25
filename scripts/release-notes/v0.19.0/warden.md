# WARDEN 0.19.0 — what the guard still missed, closed and measured

```bash
npx -y @aimarket/warden@0.19.0 scan
```

A reader asked what WARDEN still does not catch. We listed it, then attacked the flow guard with its source in hand: 17 attacks, each aimed at a documented limit. 14 got through 0.18.0; 3 get through 0.19.0, and each of those is named in the docs.

- **Keys sent in pieces or disguised.** A piece of a key from 10 characters, the key backwards, with dashes, in Cyrillic look-alike letters or base64'd in chunks is refused after outside text, even to an address the user typed. Pieces sent back to back through one argument are checked whole, card numbers too.
- **Unlabeled MCP tools that reach a person ask first**: an attendee, a collaborator, a user name, any e-mail address or IBAN. `warden-mcp flow-labels` lists the unlabeled tools your sessions used, with a labels block to correct.
- **A line under answers that drew on outside text** (Stop hook, `warden-mcp hook stop`; the Claude Code plugin registers it). An injection that only changes the answer makes no call to refuse; this tells the user where the answer came from. It never blocks.
- **Ruleset v15**: on the half of MCPTox no rule was written from, 194 of 218 poisoned tools blocked, up from 171. No new block on 45 clean servers, 999 public servers or a 1,000-package sample.
- **Re-measured on AgentDojo** on this code: 0 of 579 attack actions, 57 of 97 tasks with no question.

Still open, in the docs: an injection that only changes the answer, an address the user pastes, and pieces under 10 characters dressed as ordinary sentences. [What the flow guard does not do](https://github.com/alexar76/warden/blob/main/docs/flow-guard.md#what-it-does-not-do).

Full list: [CHANGELOG.md](https://github.com/alexar76/warden/blob/main/CHANGELOG.md).
