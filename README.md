# codex-mcp-async

**Asynchronous MCP wrapper for OpenAI Codex CLI**

Enable Claude Code to call Codex (GPT-5) asynchronously, filtering out thinking processes to save 95% context tokens.

## Features

- ✅ **Async execution** - Start Codex tasks in background, continue working
- ✅ **Context-efficient** - Filters thinking/exec logs, returns only core results
- ✅ **Full control** - Access all Codex subcommands and arguments
- ✅ **Zero config** - Works out of the box with Claude Code

## Quick Start

### 1. Prerequisites

- [Codex CLI](https://openai.com/codex) installed and authenticated
- [Claude Code](https://claude.ai/code) installed

### 2. Install

```bash
git clone https://github.com/yourusername/codex-mcp-async.git
cd codex-mcp-async
chmod +x codex_mcp_server.py
```

### 3. Configure Claude Code

Add to your `~/.claude.json`:

```json
{
  "mcpServers": {
    "codex-mcp": {
      "command": "/absolute/path/to/codex-mcp-async/codex_mcp_server.py",
      "args": [],
      "env": {}
    }
  }
}
```

> **Tip**: Use absolute path. Replace `/absolute/path/to/` with your actual path.

### 4. Restart Claude Code

Reload or restart Claude Code to load the MCP server.

## Usage

### Synchronous execution

```python
# In Claude Code conversation
mcp__codex_mcp__codex_execute(
    prompt="Write a Python function to calculate fibonacci",
    args=["--full-auto"]
)
```

### Asynchronous workflow (recommended)

```python
# Start task in background
task = mcp__codex_mcp__codex_execute_async(
    prompt="Analyze large dataset",
    args=["--full-auto"]
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
- `args` (list): Additional CLI arguments (e.g., `["--full-auto", "-m", "o3"]`)
- `timeout` (int): Optional timeout in seconds

### `codex_execute_async`
Start background task, return immediately.

**Parameters:**
- `subcommand` (str): Same as above
- `prompt` (str): Task description
- `args` (list): Additional CLI arguments

**Returns:** Task ID for later retrieval

### `codex_check_result`
Check async task status.

**Parameters:**
- `task_id` (str): Task ID from `codex_execute_async`

**Returns:**
- `running`: Task still in progress
- `completed`: Task finished with result

## Examples

### Data analysis
```python
mcp__codex_mcp__codex_execute_async(
    prompt="Read data.csv and output {rows, cols, missing_pct} as JSON",
    args=["--full-auto"]
)
```

### Code generation with stronger model
```python
mcp__codex_mcp__codex_execute(
    prompt="Write a REST API with FastAPI",
    args=["--full-auto", "-m", "o3"]
)
```

### Web search
```python
mcp__codex_mcp__codex_execute(
    prompt="Find latest Python best practices 2025",
    args=["--full-auto", "--search"]
)
```

## Architecture

```
Claude Code (you)
    ↓ calls MCP tool
codex_mcp_server.py
    ↓ spawns background process
Codex CLI (GPT-5)
    ↓ writes to /tmp/codex_tasks/{task_id}.stdout
codex_mcp_server.py
    ↓ filters thinking logs
Claude Code (receives clean result)
```

**Context savings:**
- Before: 3600 tokens (thinking + exec logs + result)
- After: 200 tokens (clean result only)
- **Savings: ~95%**

## Troubleshooting

### MCP server not showing up
- Verify absolute path in config
- Check file is executable: `chmod +x codex_mcp_server.py`
- Restart Claude Code

### Task stuck in "running"
- Check Codex process: `ps aux | grep codex`
- View task files: `ls -la /tmp/codex_tasks/`
- Task timeout: Wait 10s after file stops updating

### Zombie processes
Fixed in v0.2.0 with `start_new_session=True`

## Development

```bash
# Test server directly
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}' | python3 codex_mcp_server.py

# View task output
cat /tmp/codex_tasks/{task_id}.stdout
```

## License

MIT License - see [LICENSE](LICENSE)

## Contributing

Contributions welcome! Please open an issue or PR.

## Credits

Built for [Claude Code](https://claude.ai/code) ↔ [Codex](https://openai.com/codex) collaboration.

## Version

Current: **v0.2.0**
- Async task execution
- Zombie process fix
- File modification time detection
