"""
Tool Adapter - Bridge between tools.py registry and DSPy tools

This module adapts the legacy tools.py registry to DSPy-compatible format,
allowing a single source of truth for tool definitions.

Usage:
    from dspy_agent.tools.adapter import get_all_tools, get_definitions

    # For DSPy ReAct agent
    tools = get_all_tools()
    agent = dspy.ReAct("question -> answer", tools=tools)

    # For OpenAI function calling (legacy)
    defs = get_definitions()
"""

import functools
import logging
from typing import List, Callable, Dict, Any

log = logging.getLogger("dspy_agent")


class ToolAdapter:
    """
    Adapts tools.py registry to DSPy-compatible format.

    The adapter wraps legacy tools (which take args, ctx parameters)
    into DSPy-compatible functions (which take typed keyword arguments).

    Example:
        # Legacy tool in tools.py:
        @tool("read_file", "Read file contents", {...})
        def tool_read_file(args, ctx):
            path = args["path"]
            workspace = ctx["workspace"]
            return open(path).read()

        # Adapted for DSPy:
        def read_file(path: str, workspace: str = ".") -> str:
            '''Read file contents from workspace.'''
            return tool_read_file({"path": path}, {"workspace": workspace})
    """

    def __init__(self, legacy_registry: Dict[str, Dict], ctx: Dict[str, Any] | None = None):
        """
        Initialize adapter with legacy registry.

        Args:
            legacy_registry: The _registry dict from tools.py
            ctx: Default context (workspace, owner_id, session_key)
        """
        self._legacy_registry = legacy_registry
        self._default_ctx = ctx or {}
        self._adapted_tools: Dict[str, Callable] = {}

    def _adapt_tool(self, name: str, entry: Dict) -> Callable:
        """
        Convert a legacy tool to DSPy-compatible format.

        Legacy tools have signature: fn(args: dict, ctx: dict) -> str
        DSPy tools have signature: fn(**kwargs) -> str
        """
        legacy_fn = entry["fn"]
        definition = entry.get("definition", {})
        properties = definition.get("function", {}).get("parameters", {}).get("properties", {})
        required = definition.get("function", {}).get("parameters", {}).get("required", [])

        # Build docstring from definition
        description = definition.get("function", {}).get("description", f"Tool: {name}")
        param_docs = []
        for prop_name, prop_schema in properties.items():
            prop_type = prop_schema.get("type", "any")
            prop_desc = prop_schema.get("description", "")
            req_marker = " (required)" if prop_name in required else " (optional)"
            param_docs.append(f"    {prop_name}: {prop_type}{req_marker} - {prop_desc}")

        docstring = description
        if param_docs:
            docstring += "\n\nArgs:\n" + "\n".join(param_docs)

        @functools.wraps(legacy_fn)
        def adapted_fn(**kwargs) -> str:
            """DSPy-compatible wrapper for legacy tool."""
            # Merge default context with runtime context
            ctx = {**self._default_ctx}
            # Extract context from kwargs if provided
            for ctx_key in ["workspace", "owner_id", "session_key"]:
                if ctx_key in kwargs:
                    ctx[ctx_key] = kwargs.pop(ctx_key)

            return legacy_fn(kwargs, ctx)

        adapted_fn.__name__ = name
        adapted_fn.__doc__ = docstring

        return adapted_fn

    def get_all_tools(self) -> List[Callable]:
        """Get all adapted tools for DSPy ReAct."""
        tools = []
        for name, entry in self._legacy_registry.items():
            if name not in self._adapted_tools:
                self._adapted_tools[name] = self._adapt_tool(name, entry)
            tools.append(self._adapted_tools[name])
        return tools

    def get_definitions(self) -> List[Dict]:
        """Get OpenAI function calling definitions (passthrough from legacy)."""
        return [entry["definition"] for entry in self._legacy_registry.values()]

    def get_tool(self, name: str) -> Callable | None:
        """Get a specific adapted tool by name."""
        if name not in self._adapted_tools:
            entry = self._legacy_registry.get(name)
            if entry:
                self._adapted_tools[name] = self._adapt_tool(name, entry)
        return self._adapted_tools.get(name)


# Global adapter instance (initialized lazily)
_adapter: ToolAdapter | None = None


def _ensure_adapter() -> ToolAdapter:
    """Ensure adapter is initialized and return it."""
    global _adapter
    if _adapter is None:
        init_adapter()
    if _adapter is None:
        raise RuntimeError("Failed to initialize tool adapter")
    return _adapter


def init_adapter(ctx: Dict[str, Any] | None = None):
    """
    Initialize the global adapter with legacy registry.

    Must be called after tools.py is imported.

    Args:
        ctx: Default context (workspace, owner_id, session_key)
    """
    global _adapter
    # Import here to avoid circular dependency
    import tools
    _adapter = ToolAdapter(tools._registry, ctx or {})
    log.info(f"[adapter] Initialized with {len(tools._registry)} legacy tools")


def get_all_tools() -> List[Callable]:
    """
    Get all tools adapted for DSPy ReAct.

    Returns:
        List of DSPy-compatible tool functions
    """
    return _ensure_adapter().get_all_tools()


def get_definitions() -> List[Dict]:
    """
    Get OpenAI function calling definitions.

    Returns:
        List of tool definitions in OpenAI format
    """
    return _ensure_adapter().get_definitions()


def get_tool(name: str) -> Callable | None:
    """Get a specific adapted tool by name."""
    return _ensure_adapter().get_tool(name)
