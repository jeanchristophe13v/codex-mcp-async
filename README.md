# codex-mcp-async

**Asynchronous MCP wrapper for OpenAI Codex CLI**

Enable Claude Code to call Codex (GPT-5) asynchronously, filtering out thinking processes to save 95% context tokens.

## Features

- ✅ **Async execution** - Start Codex tasks in background, continue working
- ✅ **Context-efficient** - Filters thinking/exec logs, returns only core results
- ✅ **Full control** - Access all Codex models and reasoning efforts
- ✅ **Zero config** - Works out of the box with Claude Code

## Quick Start

### 1. Prerequisites

- [Codex CLI](https://openai.com/codex) installed and authenticated
- [Claude Code](https://claude.ai/code) installed

### 2. Install

```bash
git clone https://github.com/jeanchristophe13v/codex-mcp-async.git
cd codex-mcp-async
chmod +x codex_mcp_server.py
```

### 3. Configure Claude Code

Add to your `~/.claude.json`:

```json
{
  "mcpServers": {
    "codex-mcp": {
      "command": "python3",
      "args": ["/absolute/path/to/codex-mcp-async/codex_mcp_server.py"],
      "env": {}
    }
  }
}
```

> **Tip**: Use absolute path. Replace `/absolute/path/to/` with your actual path.

### 4. Restart Claude Code

Reload or restart Claude Code to load the MCP server.

## Usage

### Basic examples

```python
# Coding task (uses gpt-5-codex by default)
mcp__codex_mcp__codex_execute(
    prompt="Write a Python function to calculate fibonacci",
    args=["--full-auto"]
)

# Analysis task with gpt-5
mcp__codex_mcp__codex_execute(
    prompt="Analyze this dataset pattern",
    args=["--full-auto", "-m", "gpt-5"]
)

# Complex task with high reasoning
mcp__codex_mcp__codex_execute(
    prompt="Design a distributed caching system",
    args=["--full-auto", "--config", "model_reasoning_effort=high"]
)
```

### Asynchronous workflow (recommended)

```python
# Start task in background
task = mcp__codex_mcp__codex_execute_async(
    prompt="Analyze large dataset",
    args=["--full-auto", "-m", "gpt-5"]
)
# Returns: Task ID: abc123

# Continue working...
# (Claude can read docs, discuss with you, etc.)

# Check result later
result = mcp__codex_mcp__codex_check_result(task_id="abc123")
```

## Available Tools

### `codex_execute`
Synchronous execution. Blocks until Codex completes.

**Parameters:**
- `subcommand` (str): `exec`, `apply`, `resume`, `sandbox` (default: `exec`)
- `prompt` (str): Task description
- `args` (list): CLI arguments (see Model & Reasoning section)
- `timeout` (int): Optional timeout in seconds

### `codex_execute_async`
Start background task, return immediately.

**Parameters:**
- `subcommand` (str): Same as above
- `prompt` (str): Task description
- `args` (list): CLI arguments

**Returns:** Task ID for later retrieval

### `codex_check_result`
Check async task status.

**Parameters:**
- `task_id` (str): Task ID from `codex_execute_async`

**Returns:**
- `running`: Task still in progress
- `completed`: Task finished with result

## Model & Reasoning Configuration

### Models

**`gpt-5-codex` (default)**
- Best for: Coding, implementation, debugging
- Reasoning efforts: `low`, `medium` (default), `high`

**`gpt-5`**
- Best for: Analysis, planning, research
- Reasoning efforts: `minimal`, `low`, `medium` (default), `high`

### How to configure

```python
# Specify model
args=["-m", "gpt-5"]

# Specify reasoning effort
args=["--config", "model_reasoning_effort=high"]

# Combine both
args=["-m", "gpt-5", "--config", "model_reasoning_effort=minimal"]

# Always include --full-auto for non-interactive execution
args=["--full-auto", "-m", "gpt-5-codex", "--config", "model_reasoning_effort=low"]
```

### Recommended combinations

| Task Type | Model | Reasoning | Example Args |
|-----------|-------|-----------|--------------|
| Simple code | `gpt-5-codex` | `low` | `["-m", "gpt-5-codex", "--config", "model_reasoning_effort=low"]` |
| Standard coding | `gpt-5-codex` | `medium` | `["--full-auto"]` (default) |
| Complex algorithms | `gpt-5-codex` | `high` | `["--full-auto", "--config", "model_reasoning_effort=high"]` |
| Quick analysis | `gpt-5` | `minimal` | `["-m", "gpt-5", "--config", "model_reasoning_effort=minimal"]` |
| Deep analysis | `gpt-5` | `high` | `["-m", "gpt-5", "--config", "model_reasoning_effort=high"]` |

## Examples

### Data analysis (async)
```python
mcp__codex_mcp__codex_execute_async(
    prompt="Read data.csv and output {rows, cols, missing_pct} as JSON",
    args=["--full-auto", "-m", "gpt-5"]
)
```

### Complex code generation
```python
mcp__codex_mcp__codex_execute(
    prompt="Implement a thread-safe LRU cache in Python",
    args=["--full-auto", "--config", "model_reasoning_effort=high"]
)
```

### Web search + analysis
```python
mcp__codex_mcp__codex_execute(
    prompt="Find and summarize latest FastAPI best practices",
    args=["--full-auto", "--search", "-m", "gpt-5"]
)
```

## Architecture

```
Claude Code (you)
    ↓ calls MCP tool
codex_mcp_server.py
    ↓ spawns background process
Codex CLI (GPT-5 / GPT-5-Codex)
    ↓ writes to /tmp/codex_tasks/{task_id}.stdout
codex_mcp_server.py
    ↓ filters thinking logs
Claude Code (receives clean result)
```

**Context savings:**
- Before: 3600 tokens (thinking + exec logs + result)
- After: 200 tokens (clean result only)
- **Savings: ~95%**

## Important Notes

### Git repository check

The MCP server **automatically adds** `--skip-git-repo-check` to all codex commands. This allows tasks to run in `/tmp` directory without git repository errors.

If you're calling codex CLI directly (outside this MCP server), add the flag manually:
```bash
codex exec "your prompt" --full-auto --skip-git-repo-check
```

### Required arguments

Always include `--full-auto` in `args` for non-interactive execution:
```python
args=["--full-auto"]  # Minimum required
args=["--full-auto", "-m", "gpt-5"]  # With model selection
```

## Troubleshooting

### MCP server not showing up
- Verify absolute path in config
- Check file is executable: `chmod +x codex_mcp_server.py`
- Restart Claude Code

### Task completes in 0s with no output
- **Fixed in v0.2.1** - The server now auto-adds `--skip-git-repo-check`
- If using older version, update to latest release

### Task stuck in "running"
- Wait 10s after file stops updating
- Check task files: `ls -la /tmp/codex_tasks/`

### Invalid model error
- Use `gpt-5-codex` or `gpt-5` (not `o3` or other names)
- Don't append reasoning effort to model name

## License

MIT License - see [LICENSE](LICENSE)

## Contributing

Contributions welcome! Please open an issue or PR.

## Credits

Built for [Claude Code](https://claude.ai/code) ↔ [Codex](https://openai.com/codex) collaboration.

## Version

Current: **v0.2.1**
- Fixed async task execution in non-git directories
- Auto-added `--skip-git-repo-check` flag to all commands
- Resolved "Not inside a trusted directory" error

Previous: **v0.2.0**
- Async task execution
- Zombie process fix
- File modification time detection
