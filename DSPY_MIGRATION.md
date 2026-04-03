# DSPy Agent Migration Guide

This document describes the migration from the original agent system to DSPy-based architecture.

## Quick Start

```bash
# Install DSPy dependencies
pip install -r requirements-dspy.txt

# Run DSPy agent
python3 dspy_xiaowang.py
```

## Architecture Comparison

### Original Architecture (llm.py)

```
User Message → Manual LLM API Call → Parse Tool Calls → Execute Tools → Loop
```

### DSPy Architecture (dspy_agent/)

```
User Message → DSPy ReAct Module → Automatic Tool Selection → Execute Tools → Response
```

## Key Differences

| Aspect | Original | DSPy |
|--------|----------|------|
| LLM Calls | Manual urllib.request | DSPy LM abstraction |
| Tool Loop | Custom while loop | dspy.ReAct handles automatically |
| Prompts | String concatenation | Declarative Signatures |
| Optimization | None | Teleprompter (MIPROv2) |
| Memory | Custom vector search | DSPy RAG modules |

## File Structure

```
dspy_agent/
├── __init__.py          # Package entry point
├── signatures/          # DSPy Signatures (input/output definitions)
│   └── __init__.py
├── modules/             # DSPy Modules (core logic)
│   └── __init__.py
├── tools/               # DSPy-compatible tools
│   └── __init__.py
└── utils/               # Optimization and helpers
    └── __init__.py

dspy_xiaowang.py         # New entry point
requirements-dspy.txt    # DSPy dependencies
```

## Migration Steps

### 1. Tools Migration

Original (tools.py):
```python
@tool("exec", "Execute shell command", {...}, ["command"])
def tool_exec(args, ctx):
    return subprocess.run(args["command"], ...)
```

DSPy (dspy_agent/tools/):
```python
@registry.register
def exec(command: str, timeout: int = 60) -> str:
    """Execute a shell command."""
    return subprocess.run(command, ...)
```

### 2. LLM Calls Migration

Original (llm.py):
```python
def _call_llm(messages, tool_defs):
    provider = _get_provider()
    url = provider["api_base"] + "/chat/completions"
    body = {"model": provider["model"], "messages": messages, "tools": tool_defs}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={...})
    return json.loads(urllib.request.urlopen(req).read())
```

DSPy (dspy_agent/modules/):
```python
# Just configure once
dspy.configure(lm=dspy.LM("openai/gpt-4o-mini"))

# Use in module
class ToolAgent(dspy.Module):
    def __init__(self):
        self.react = dspy.ReAct("question -> answer", tools=[...])
```

### 3. Memory Migration

Original (memory.py):
```python
def retrieve(user_msg, session_key):
    query_vec = _embed([user_msg])
    results = _table.search(query_vec[0]).limit(top_k).to_list()
    return format_results(results)
```

DSPy (dspy_agent/modules/):
```python
class MemoryModule(dspy.Module):
    def forward(self, query, session_key):
        # DSPy handles embedding and retrieval
        result = self.retrieval(query=query)
        return self.synthesis(query=query, memories=result)
```

## New Features

### 1. Teleprompter Optimization

```python
from dspy_agent.utils import optimize_agent

# Collect training examples
trainset = [
    {"user_request": "Hello", "response": "Hi there!"},
    {"user_request": "Search for Python", "response": "..."},
]

# Optimize agent
optimized = optimize_agent(
    agent,
    trainset=trainset,
    metric=my_metric,
    auto="medium"
)

# Save for future use
optimized.save("optimized_agent.json")
```

### 2. RAG Memory

```python
from dspy_agent.modules import MemoryModule

memory = MemoryModule(retrieve_fn=custom_retriever)
context = memory(query="What did we discuss?")
# context.memory_context can be injected into agent
```

### 3. Tool Trajectory Inspection

```python
result = agent(user_request="Search for weather")
print(result.trajectory)  # Shows all reasoning steps
```

## Configuration

DSPy uses the same config.json format. Just point to it:

```bash
export AGENT_CONFIG=/path/to/config.json
python3 dspy_xiaowang.py
```

For optimized agents:

```bash
export DSPY_OPTIMIZED=/path/to/optimized_state.json
python3 dspy_xiaowang.py
```

## Backward Compatibility

- Original `xiaowang.py` continues to work
- Original `tools.py` can be imported alongside DSPy tools
- Messaging integration remains unchanged
- Session files are compatible

## Performance Considerations

| Metric | Original | DSPy |
|--------|----------|------|
| First call latency | ~2s | ~2s (same LLM) |
| Memory overhead | Low | Medium (DSPy caching) |
| Optimization time | N/A | 5-30 min depending on auto level |

## Troubleshooting

### "No module named 'dspy'"
```bash
pip install dspy>=2.5.0
```

### "API key not found"
Ensure config.json has valid API keys, or set environment variables:
```bash
export DSPY_API_KEY=your-key
export DSPY_MODEL=openai/gpt-4o-mini
```

### "Tool not found in registry"
Tools are auto-registered when importing dspy_agent.tools:
```python
from dspy_agent.tools import registry, get_all_tools
tools = get_all_tools()  # Returns all registered tools
```

## Further Reading

- [DSPy Documentation](https://dspy.ai/)
- [DSPy GitHub](https://github.com/stanfordnlp/dspy)
- [Teleprompter Guide](https://dspy.ai/learn/optimization)
