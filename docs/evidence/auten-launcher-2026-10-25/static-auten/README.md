<p align="center">
  <a href="https://auten.ai/mcp"><img src="assets/banner.png" alt="Auten: computer use MCP server" width="720" /></a>
</p>

<h1 align="center">Auten MCP server</h1>

<p align="center">
  <b>Computer use for the AI agent you already have.</b><br />
  Claude Code, Codex, Cursor, Gemini CLI or any MCP client can click, type and read the screen
  on your Mac, Windows or Linux computer — and your Android phone (beta) — in real apps that have no API.
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@autenai/mcp"><img src="https://img.shields.io/npm/v/@autenai/mcp?color=00997A&label=npm" alt="npm" /></a>
  <a href="https://cursor.com/en/install-mcp?name=auten&config=eyJjb21tYW5kIjoibnB4IiwiYXJncyI6WyIteSIsIkBhdXRlbmFpL21jcCJdfQ%3D%3D"><img src="https://cursor.com/deeplink/mcp-install-dark.svg" alt="Add Auten to Cursor" height="20" /></a>
  <a href="https://vscode.dev/redirect/mcp/install?name=auten&config=%7B%22command%22%3A%22npx%22%2C%22args%22%3A%5B%22-y%22%2C%22%40autenai%2Fmcp%22%5D%7D"><img src="https://img.shields.io/badge/VS_Code-Add_Auten-0098FF?logo=visualstudiocode&logoColor=white" alt="Add Auten to VS Code" /></a>
</p>

<p align="center">
  <a href="https://auten.ai/mcp">Website</a> &nbsp;|&nbsp;
  <a href="https://auten.ai/connect">Setup for every client</a> &nbsp;|&nbsp;
  <a href="https://auten.ai/pricing">Pricing</a> &nbsp;|&nbsp;
  <a href="mailto:hello@auten.ai">hello@auten.ai</a>
</p>

<p align="center">
  <img src="assets/demo.gif" alt="Animation: Claude Code asks Auten to reply on Instagram; Auten opens the app, finds the chat and sends. The next run replays the same task from memory in seconds, with no tokens." width="720" /><br />
  <sub>Illustration: the first run is driven by your AI, the next runs replay from memory.</sub>
</p>

---

Auten is the hands, your AI is the brain. A small runner on your computer does the clicking,
typing and screen reading. Your agent talks to it over MCP (stdio or SSE). Auten does not ship
its own model and never needs your AI key; your agent keeps using the plan you already pay for.

What makes it different from a plain mouse and keyboard bridge:

- **Reads the UI, not just pixels.** It uses the accessibility tree, so your agent gets a numbered
  list of real buttons and fields (`list_elements` then `click_at(3)`) instead of guessing
  coordinates. OCR and real screenshots are there when an app has no accessibility info.
- **Learns a task once, replays it without AI.** After your agent finishes a task, Auten can save
  it as a skill. The next run replays in seconds, with no tokens spent, and fixes itself when the
  app's layout changes.
- **Passwords stay on your machine.** `fill_login` types a stored secret into a field without the
  agent ever seeing the value.

<p align="center">
  <img src="assets/real-replay.gif" alt="Real screen capture: an AI agent fills a local contact form through Auten MCP in about 14 seconds and saves it as a skill; run_skill then replays it with new values in 4.8 seconds without calling the model." width="640" /><br />
  <sub>Real capture, not an illustration: first run by the agent (~14 s incl. thinking), then <code>run_skill</code> with new values (4.8 s, no model call). Local test page, 1 fps, one cut between the runs.</sub>
</p>

## What you can ask your agent

Plain requests in the client you already use. The agent decides the steps, Auten does the clicks.

- "Open the supplier portal, download this month's invoices and put them in ~/Invoices."
- "Go through the new leads in the CRM and fill in the missing company names from their emails."
- "Export the report from that desktop app as CSV. It has no API, so use the File menu."
- "On my Android phone, open Instagram and reply to the latest DM with this text." (phone is beta, over USB)
- "That worked. Save it as a skill called `export-report`." Next time: "Run `export-report`." It replays without AI.

## Quick start

**1. Install the runner** (one command; no admin rights on macOS and Windows, on Linux it asks for `sudo` once to apt-install the accessibility and input tools):

```bash
# macOS and Linux
curl -fsSL https://auten.ai/install | bash
```

```powershell
# Windows (PowerShell)
irm https://auten.ai/install.ps1 | iex
```

The first run asks you to connect a free key (30 minutes every month, no card).

**2. Add Auten to your agent.** For Claude Code, Auten can do it by itself:

```bash
auten connect
```

or add it with the Claude Code CLI and check with `/mcp`:

```bash
claude mcp add -s user auten -- auten mcp-bridge
```

**3. Ask in plain words.** For example: *"Open Figma, export the Hero frame as PNG to my Desktop"*
or *"Go through the unread invoices in my mail and fill them into the accounting app"*.
More prompts for computer and phone (beta) tasks: [examples/prompts.md](examples/prompts.md).

### Or run it through npx

Any client that can start an npm package can use the launcher instead. It starts the installed
runner, and if Auten is not installed yet it tells your agent the one-line install command.
The "Add to Cursor" and "VS Code" buttons at the top add exactly this entry.

```json
{
  "mcpServers": {
    "auten": { "command": "npx", "args": ["-y", "@autenai/mcp"] }
  }
}
```

```bash
claude mcp add -s user auten -- npx -y @autenai/mcp
```

On Windows, if the client reports `spawn npx ENOENT`: npx is `npx.cmd` there, and some clients start
servers without a shell. Use `"command": "cmd", "args": ["/c", "npx", "-y", "@autenai/mcp"]`
(Claude Code: `claude mcp add -s user auten -- cmd /c npx -y @autenai/mcp`), or the direct
`auten mcp-bridge` entry below.

### Or as a Claude Code plugin

This repository is also a plugin marketplace. Inside Claude Code:

```
/plugin marketplace add auten-ai/auten-mcp
/plugin install auten@auten
```

The plugin adds the same npx launcher entry, nothing else (no hooks or commands). See [plugin/README.md](plugin/README.md).

## Client setup

Every client starts the same stdio command: `auten mcp-bridge` (or `npx -y @autenai/mcp`). If your app says it cannot find
`auten`, use the full path from `which auten` (usually `~/.local/bin/auten`).

<details>
<summary><b>OpenAI Codex</b></summary>

```bash
codex mcp add auten -- auten mcp-bridge
```

or in `~/.codex/config.toml`:

```toml
[mcp_servers.auten]
command = "auten"
args = ["mcp-bridge"]
```
</details>

<details>
<summary><b>Cursor</b></summary>

`~/.cursor/mcp.json` (or `.cursor/mcp.json` in a project):

```json
{
  "mcpServers": {
    "auten": { "command": "auten", "args": ["mcp-bridge"] }
  }
}
```
</details>

<details>
<summary><b>Gemini CLI</b></summary>

```bash
gemini mcp add --scope user auten auten mcp-bridge
```

or the same `mcpServers` entry in `~/.gemini/settings.json`.
</details>

<details>
<summary><b>Claude Desktop</b></summary>

Settings, Developer, Edit Config
(`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS,
`%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "auten": { "command": "auten", "args": ["mcp-bridge"] }
  }
}
```

Restart Claude Desktop.
</details>

<details>
<summary><b>VS Code (GitHub Copilot agent mode)</b></summary>

Run `MCP: Open User Configuration` and add:

```json
{
  "servers": {
    "auten": { "type": "stdio", "command": "auten", "args": ["mcp-bridge"] }
  }
}
```
</details>

<details>
<summary><b>Windsurf</b></summary>

`~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "auten": { "command": "auten", "args": ["mcp-bridge"] }
  }
}
```
</details>

<details>
<summary><b>Zed</b></summary>

`~/.config/zed/settings.json`:

```json
{
  "context_servers": {
    "auten": { "command": "auten", "args": ["mcp-bridge"] }
  }
}
```
</details>

<details>
<summary><b>Cline</b></summary>

Ask Cline to set Auten up from [llms-install.md](llms-install.md), or add it yourself in
MCP Servers, Configure (`cline_mcp_settings.json`):

```json
{
  "mcpServers": {
    "auten": { "command": "auten", "args": ["mcp-bridge"] }
  }
}
```
</details>

<details>
<summary><b>Remote (SSE) instead of stdio</b></summary>

For clients that connect over the network, keep the runner online on the computer it should
control:

```bash
auten --runner-only
```

Then use your personal MCP URL from your [account page](https://auten.ai/account). It contains
your key, so keep it private.

```bash
claude mcp add --transport sse auten <your-url>
```
</details>

No agent? Give the auten CLI your own key (Anthropic, OpenAI, Google, DeepSeek or any
OpenAI-compatible provider) with `auten key add`, then run `auten "open my calendar and tell me what is next"`.

## Tools

| Group | Tools |
|---|---|
| See the screen | `list_elements`, `read_text`, `screenshot`, `screenshot_labeled`, `vision`, `screen_info` |
| Act | `click_at`, `click`, `fill`, `type`, `paste_text`, `press_keys`, `scroll`, `drag`, `move_mouse`, `act_on_matching`, `menu_select` |
| Apps and windows | `open_app`, `open_url`, `focus_window`, `browser_tabs`, `save_file`, `upload_file`, `clipboard_read` |
| Secrets | `list_logins`, `fill_login`, `get_profile` |
| Learned skills | `list_skills`, `run_skill`, `skills`, `show_skill`, `start_recording`, `stop_recording`, `start_fixing`, `stop_fixing` |
| Coordination | `ask_user`, `focus_app`, `release`, `gui_status`, `wait`, `opened_items`, `browser_cleanup` |

## Platforms

macOS (Apple Silicon and Intel), Windows 10/11, Linux (X11), plus an Android phone over USB (beta).

**Linux: installer stops at the "deps" step?** It needs `sudo` once for the accessibility (AT-SPI) and input tools.
On a fresh or minimal box (empty apt lists, no `python3-venv`) install them first, then run the installer again:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pyatspi python3-gi xdotool wmctrl scrot xclip libglib2.0-bin tesseract-ocr libsecret-tools
```

Auten drives a real X11 desktop session, so a headless container without a display won't work.
Still stuck? Paste the last lines in [Discussions](https://github.com/auten-ai/auten-mcp/discussions).

## Pricing

| Plan | Runtime | Price |
|---|---|---|
| Free | 30 min every month | €0, no card |
| Starter | 10 h every month | €9/month (early access) |
| Pro | Unlimited | €29/month (early access) |

You bring your own AI, so the price is for Auten only. Details on [auten.ai/pricing](https://auten.ai/pricing).

## Privacy and safety

- The runner only acts when your MCP client calls a tool. Nothing runs in the background on its own.
- Stored passwords live in the system keychain (macOS, Windows) or a private local vault (Linux)
  and never reach our servers or the model. A secret that shows up on screen is replaced with a
  placeholder before your agent sees it.
- Each saved login is pinned to the site or app where it was first used. On any other origin
  `fill_login` refuses and types nothing; only you can re-pin it (`auten vault unpin <name>`).
- Your activity history and learned skills are written to your own computer, not ours.
  See the [privacy policy](https://auten.ai/privacy).

## About this repository

This repository holds the public docs, client configs and the `@autenai/mcp` npm launcher
(`bin/auten-mcp.js`), all under the MIT [LICENSE](LICENSE). The runner itself is distributed
separately through the installers above, under the [Auten terms of service](https://auten.ai/terms). Questions, bugs and feature requests are
welcome as [issues](https://github.com/auten-ai/auten-mcp/issues) or at hello@auten.ai.

Auten is made by [MB Icecode](https://icecode.lt), Lithuania.
