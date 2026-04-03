"""
DSPy-based AI Agent System

A refactored version of the 7/24 Office agent using DSPy framework.
This module provides:
- Declarative Signatures for input/output specification
- Modular DSPy Modules for composable AI programs
- ReAct agent with tool support
- RAG-based memory retrieval
- Teleprompter optimization support

Usage:
    from dspy_agent import Agent, ToolRegistry

    agent = Agent(tools=[...])
    result = agent(user_request="Hello")
"""

from .signatures import *
from .modules import *
from .tools import *
from .utils import *

__version__ = "2.0.0"
__all__ = [
    # Signatures
    "AgentSignature",
    "ToolSelectionSignature",
    "MemoryCompressionSignature",
    "MemoryRetrievalSignature",

    # Modules
    "Agent",
    "ToolAgent",
    "MemoryModule",
    "ScheduledAgent",

    # Tools
    "ToolRegistry",
    "create_tool",

    # Utils
    "configure_lm",
    "optimize_agent",
]
