# dexcom-agent-tools

An MCP server and an agent skill that let an AI agent read and analyze your Dexcom CGM data.

- **MCP server** (`dexcom-mcp`, stdio) exposes these tools:
  - `get_current_glucose`: the latest reading, its trend arrow, and its age in minutes
  - `get_glucose(start, end)`: readings between two ISO 8601 timestamps, within the last 24 hours
  - `get_glucose_stats(start, end, target_low_mg_dl, target_high_mg_dl)`: mean, SD, CV, GMI, min/max, and the percentage of time in, below, and above range (TIR/TBR/TAR). Defaults to a 70–180 mg/dL range.
- **Skill** `skills/analyze-glucose-patterns`: tells an agent how to call these tools and explain your patterns in plain language.

The backend is **Dexcom Share**, which updates in near real time, through [`pydexcom`](https://github.com/gagebenne/pydexcom). It supports the US, outside-US (`ous`), and Japan (`jp`) regions, and reports in mg/dL (the default) or mmol/L.

> ⚠️ **Disclaimer.** This is not a medical device. The Dexcom Share API is unofficial and undocumented, and it can change or break without notice. Data can be delayed, missing, or wrong. **Don't make treatment or dosing decisions from this.** Use your receiver, the Dexcom app, or a fingerstick. Dexcom's official OAuth API is about 1 hour delayed in the US and isn't supported in v1.

## Prerequisites

1. In the Dexcom app, turn on **Share** and invite at least one follower. If nobody follows you, the Share API returns no data.
2. Use your own Dexcom account username (or email) and password. A follower's own login doesn't work.
3. Install Python 3.10+ and [uv](https://docs.astral.sh/uv/). Plain pip also works.

## Setup

```bash
cd ~/Projects/dexcom-agent-tools
cp .env.example .env        # then fill in DEXCOM_USERNAME / DEXCOM_PASSWORD
uv sync --extra dev         # or: python -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
```

### Environment variables

Credentials are read **only** from the environment. The server doesn't load `.env` itself. Export the variables, or pass them through your MCP client config.

| Variable | Default | Notes |
|---|---|---|
| `DEXCOM_USERNAME` | (required) | Dexcom account username, email, or phone (`+1...`) |
| `DEXCOM_ACCOUNT_ID` | (none) | Optional. Use this instead of the username. |
| `DEXCOM_PASSWORD` | (required) | |
| `DEXCOM_REGION` | `us` | `us`, `ous` (outside US), or `jp` |
| `DEXCOM_UNITS` | `mg/dL` | `mg/dL` or `mmol/L` |
| `DEXCOM_TARGET_LOW` / `DEXCOM_TARGET_HIGH` | `70` / `180` | Stats range, always in mg/dL |
| `DEXCOM_DRY_RUN` | `0` | Set to `1` to serve synthetic data with no credentials or network |

## Run

```bash
# Check the config without starting the server (exits 2 with a clear message if credentials are missing)
set -a; . ./.env; set +a
uv run dexcom-mcp --check

# Try it with fake data
DEXCOM_DRY_RUN=1 uv run dexcom-mcp --check

# Run the MCP server on stdio (normally your MCP client starts it)
uv run dexcom-mcp            # or: uv run python -m dexcom_agent_tools

# Tests (no network)
uv run pytest -q

# Interactive inspector (optional)
npx @modelcontextprotocol/inspector uv --directory ~/Projects/dexcom-agent-tools run dexcom-mcp
```

## Add to an MCP client

**Cursor**: put this in `~/.cursor/mcp.json` (global) or in `.cursor/mcp.json` inside a project. **Claude Desktop**: put it in `~/Library/Application Support/Claude/claude_desktop_config.json`.

```json
{
  "mcpServers": {
    "dexcom": {
      "command": "uv",
      "args": ["--directory", "/Users/YOU/Projects/dexcom-agent-tools", "run", "dexcom-mcp"],
      "env": {
        "DEXCOM_USERNAME": "you@example.com",
        "DEXCOM_PASSWORD": "…",
        "DEXCOM_REGION": "us",
        "DEXCOM_UNITS": "mg/dL"
      }
    }
  }
}
```

The JSON file holds your password in plain text, so keep it out of git. Or skip the `env` block and point `command` at a small wrapper script that loads the secrets from your keychain.

**Claude Code**:

```bash
claude mcp add dexcom -e DEXCOM_USERNAME=... -e DEXCOM_PASSWORD=... -- \
  uv --directory ~/Projects/dexcom-agent-tools run dexcom-mcp
```

## Install the skill

The skill is a plain `SKILL.md` file with no secrets in it. Copy or symlink it into your agent's skills folder:

```bash
# Claude Code (personal skills)
mkdir -p ~/.claude/skills && ln -s ~/Projects/dexcom-agent-tools/skills/analyze-glucose-patterns ~/.claude/skills/
# Cursor / other agents: add skills/analyze-glucose-patterns/SKILL.md as a rule or skill
```

Then ask your agent something like *"analyze my glucose patterns from the last 24h"* or *"how was my overnight?"*

## Tool details

- Times are ISO 8601. A timestamp with no timezone is read as the server's local time. Output times use local time with the UTC offset included.
- Share only keeps the **last 24 hours** at 5-minute intervals (up to 288 readings). A window that reaches back further gets trimmed to 24 hours. A window that ends more than 24 hours ago returns an error.
- `get_current_glucose` falls back to the newest reading in the last 24 hours. Check `age_minutes` to see how stale it is.
- Stats percentages count readings. `coverage_percent` shows how much of the window actually has data.
- If you need history beyond 24 hours, log the readings locally or add the official API later (open item for v2).

## Layout

```
src/dexcom_agent_tools/
  config.py   # env settings, unit conversion
  source.py   # Dexcom Share client (pydexcom) + synthetic dry-run source
  stats.py    # TIR/TBR/TAR, mean, SD, CV, GMI
  server.py   # MCP tools + CLI (--check)
skills/analyze-glucose-patterns/SKILL.md
tests/
```

## License

MIT
