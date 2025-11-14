# Codex MCP Async Server

**Asynchronous MCP wrapper for OpenAI Codex CLI with 95% context savings**

Enable Claude Code to call Codex (GPT-5) asynchronously, filtering out thinking processes to save 95% context tokens.

## Features

- ✅ **Async execution** - Start Codex tasks in background, continue working
- ✅ **Context-efficient** - Filters thinking/exec logs, returns only core results
- ✅ **Full control** - Access all Codex models and reasoning efforts
- ✅ **Zero config** - Works out of the box with Claude Code

## Quick Start

### 🚀 Install with UVX

Zero configuration - just run:

```bash
uvx codex-mcp-async
```

### Configure Claude Code

Add to your `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "codex-mcp": {
      "command": "uvx",
      "args": ["codex-mcp-async"],
      "env": {}
    }
  }
}
```

> **Or use the provided config**: Copy `mcp-config.json` to your Claude settings directory

### Restart Claude Code

Reload or restart Claude Code to load the MCP server.

## Usage Examples

### 🚀 Async Execution (Game Changer!)

Start a long Codex task and continue working immediately:

**You:**
> Please analyze this entire codebase and generate comprehensive documentation

**Claude:**
I'll analyze your entire codebase and generate comprehensive documentation. This is a large task, so I'll start it asynchronously...

✅ **Task Started** (Task ID: abc12345)
You can continue working on other things while it runs in the background!

**You:** (Continue working immediately)
> While the documentation is being generated, help me fix this bug

**Claude:**
Sure! Let me help you fix that bug...

**You:** (A few minutes later)
> Can you check if the documentation task is finished?

**Claude:**
✅ **Documentation Complete!**

[View Generated Documentation]
- API reference
- Code examples
- Architecture overview
- Setup instructions

### ⚡ Parallel Execution

Run multiple Codex tasks simultaneously:

**You:**
> I need to do three things at once:
> 1. Generate unit tests for utils.py
> 2. Refactor database.py to use async/await
> 3. Add type hints to all functions in api.py

**Claude:**
I'll start all three tasks in parallel!

🔄 **Task 1 Started** (Task ID: task1) - Generating unit tests
🔄 **Task 2 Started** (Task ID: task2) - Refactoring database code
🔄 **Task 3 Started** (Task ID: task3) - Adding type hints

All tasks are running in parallel...

**You:** (Later)
> Are all three tasks finished?

**Claude:**
✅ **All Complete!**

- ✅ Task 1: Unit tests for utils.py generated
- ✅ Task 2: database.py refactored to async mode
- ✅ Task 3: Type hints added to api.py functions

### 🎯 Quick Sync Tasks

For simple immediate tasks:

**You:**
> Write a Python function to validate email addresses

**Claude:**
```python
import re

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

# Usage examples
print(validate_email("user@example.com"))  # True
print(validate_email("invalid-email"))    # False
```

✅ **Task Complete!**

### 🧠 Model Selection

**You:**
> Analyze this research paper using GPT-5 with high reasoning

**Claude:**
```python
# Uses analysis model instead of coding model
mcp__codex_mcp__codex_execute(
    prompt="Analyze this research paper on machine learning",
    args=["--full-auto", "-m", "gpt-5", "--config", "model_reasoning_effort=high"]
)
```

## Why Async + Context Filtering?

**Problem 1:** Codex blocks Claude Code while running.
**Problem 2:** Codex outputs 3000+ tokens of thinking logs for every task.

**Solution:** This MCP server runs Codex asynchronously and filters out 95% of the noise.

**Benefits:**
- 🚀 Start a task and continue working immediately
- ⚡ Run multiple tasks in parallel
- 💾 95% context savings (3000 tokens → 150 tokens)
- 🎯 Clean, focused results only
- 🧹 Automatic process cleanup

## Advanced Usage

### Model Selection

**`gpt-5-codex` (default)** - Best for coding, debugging, implementation
**`gpt-5`** - Best for analysis, planning, research

### Reasoning Levels
- `minimal/low` - Quick tasks
- `medium` - Standard work (default)
- `high` - Complex problems

### Example Configurations

```python
# Quick coding task
args=["--full-auto", "--config", "model_reasoning_effort=low"]

# Complex analysis
args=["--full-auto", "-m", "gpt-5", "--config", "model_reasoning_effort=high"]

# Web search + analysis
args=["--full-auto", "--search", "-m", "gpt-5"]
```

## Architecture & Performance

```
Claude Code (you)
    ↓ calls MCP tool
codex-mcp-async (runs Codex in background)
    ↓ filters thinking logs (95% savings!)
Codex CLI (GPT-5)
    ↓ returns clean result
Claude Code (receives focused output)
```

**Context Savings:**
- Before: 3600 tokens (thinking + logs + result)
- After: 180 tokens (clean result only)
- **95% reduction!**

## Troubleshooting

**Server not showing up?**
- Check: `uvx codex-mcp-async` runs without errors
- Restart Claude Code after config change

**Task stuck in "running"?**
- Large tasks take time to complete
- Check debug logs: `/tmp/codex_mcp_debug.log`

**Context too large?**
- Enable filtering: Always use async mode for long tasks
- Split large tasks into smaller chunks

## Requirements

- Python 3.8+
- [Codex CLI](https://openai.com/codex) installed and authenticated
- [Claude Code](https://claude.ai/code)
- [uvx](https://github.com/astral-sh/uvx) (for easy installation)

## License

MIT License - see [LICENSE](LICENSE)

---

**Questions?** Open an issue on GitHub.

**Made with ❤️ for the Claude Code + Codex community**
