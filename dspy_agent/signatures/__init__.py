"""
DSPy Signatures for AI Agent

This module defines all the declarative signatures used by the agent system.
Each signature specifies inputs, outputs, and optional instructions for LLM tasks.

Based on DSPy best practices:
- Use class-based signatures for complex tasks with descriptions
- Use type hints for better validation
- Include docstrings as natural language instructions
"""

import dspy
from typing import Optional, List, Dict, Any


# ============================================================
#  Core Agent Signatures
# ============================================================

class AgentSignature(dspy.Signature):
    """You are a helpful AI assistant that processes user requests using available tools.

    Analyze the user's request and provide a helpful response. Use tools when necessary
    to accomplish tasks. Be concise and helpful.
    """

    user_request: str = dspy.InputField(desc="The user's message or request")
    conversation_history: str = dspy.InputField(desc="Previous conversation context")
    available_tools: str = dspy.InputField(desc="List of available tools and their descriptions")
    memory_context: str = dspy.InputField(desc="Relevant memories retrieved from long-term storage")

    response: str = dspy.OutputField(desc="Your response to the user")
    tool_calls: Optional[List[Dict[str, Any]]] = dspy.OutputField(
        desc="List of tool calls to execute, each with 'name' and 'arguments'",
        default=None
    )


class ToolSelectionSignature(dspy.Signature):
    """Select the most appropriate tool to accomplish a task.

    Given a user request and available tools, determine which tool(s) to use
    and what arguments to pass. If no tool is needed, return empty.
    """

    user_request: str = dspy.InputField(desc="The task to accomplish")
    available_tools: str = dspy.InputField(desc="Tool names and their descriptions")
    context: str = dspy.InputField(desc="Additional context from conversation")

    selected_tool: Optional[str] = dspy.OutputField(desc="Name of the tool to use, or None")
    tool_arguments: Optional[Dict[str, Any]] = dspy.OutputField(desc="Arguments for the tool")
    reasoning: str = dspy.OutputField(desc="Why this tool was selected")


# ============================================================
#  Memory System Signatures
# ============================================================

class MemoryCompressionSignature(dspy.Signature):
    """Extract structured, memorable facts from conversation.

    Focus on information with long-term value:
    - User preferences and habits
    - Important facts and decisions
    - Contact information and relationships
    - Plans and commitments

    Skip:
    - Chitchat and greetings
    - Pure tool call results
    - Redundant confirmations
    """

    conversation: str = dspy.InputField(desc="Conversation messages to compress")

    memories: List[Dict[str, Any]] = dspy.OutputField(
        desc="List of extracted memories, each with 'fact', 'keywords', 'persons', 'timestamp', 'topic'"
    )


class MemoryRetrievalSignature(dspy.Signature):
    """Determine what memories are relevant to the current query."""

    query: str = dspy.InputField(desc="User's current question or request")
    conversation_context: str = dspy.InputField(desc="Recent conversation messages")

    search_keywords: List[str] = dspy.OutputField(desc="Keywords to search in memory")
    memory_relevance: str = dspy.OutputField(desc="Why these memories might be relevant")


class MemorySynthesisSignature(dspy.Signature):
    """Synthesize retrieved memories into context for response generation."""

    user_query: str = dspy.InputField(desc="Current user request")
    retrieved_memories: str = dspy.InputField(desc="Memories retrieved from storage")

    memory_context: str = dspy.OutputField(
        desc="Concise summary of relevant memories to include in system prompt"
    )


# ============================================================
#  Scheduler Signatures
# ============================================================

class ScheduledTaskExecutionSignature(dspy.Signature):
    """Execute a scheduled task and determine the response."""

    task_name: str = dspy.InputField(desc="Name of the triggered task")
    task_message: str = dspy.InputField(desc="Original task message/instructions")
    current_context: str = dspy.InputField(desc="Current system state and context")

    action: str = dspy.OutputField(desc="What action to take")
    response: str = dspy.OutputField(desc="Message to send to user if applicable")


