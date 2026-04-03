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
from typing import Optional, List, Dict, Any, Literal


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


class ToolExecutionSignature(dspy.Signature):
    """Execute a tool and summarize the result."""

    tool_name: str = dspy.InputField(desc="Name of the tool being executed")
    tool_arguments: Dict[str, Any] = dspy.InputField(desc="Arguments passed to the tool")
    tool_result: str = dspy.InputField(desc="Raw output from tool execution")

    summary: str = dspy.OutputField(desc="Concise summary of the tool result")
    success: bool = dspy.OutputField(desc="Whether the tool executed successfully")
    follow_up_needed: bool = dspy.OutputField(desc="Whether additional action is needed")


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

class ScheduleCreationSignature(dspy.Signature):
    """Parse a natural language scheduling request into structured task data."""

    user_request: str = dspy.InputField(desc="User's scheduling request in natural language")
    current_time: str = dspy.InputField(desc="Current date and time")

    task_name: str = dspy.OutputField(desc="Unique identifier for the task")
    task_message: str = dspy.OutputField(desc="Message to process when task triggers")
    delay_seconds: Optional[int] = dspy.OutputField(desc="Delay for one-shot tasks")
    cron_expr: Optional[str] = dspy.OutputField(desc="Cron expression for recurring tasks")
    is_recurring: bool = dspy.OutputField(desc="Whether this is a recurring task")


class ScheduledTaskExecutionSignature(dspy.Signature):
    """Execute a scheduled task and determine the response."""

    task_name: str = dspy.InputField(desc="Name of the triggered task")
    task_message: str = dspy.InputField(desc="Original task message/instructions")
    current_context: str = dspy.InputField(desc="Current system state and context")

    action: str = dspy.OutputField(desc="What action to take")
    response: str = dspy.OutputField(desc="Message to send to user if applicable")


# ============================================================
#  Self-Check Signatures
# ============================================================

class SelfCheckSignature(dspy.Signature):
    """Analyze system health and generate a diagnostic report."""

    session_stats: str = dspy.InputField(desc="Today's conversation statistics")
    error_logs: str = dspy.InputField(desc="Recent error log entries")
    system_metrics: str = dspy.InputField(desc="Memory, disk, uptime metrics")
    scheduled_tasks: str = dspy.InputField(desc="Status of scheduled tasks")

    health_status: Literal["healthy", "warning", "critical"] = dspy.OutputField()
    issues_found: List[str] = dspy.OutputField(desc="List of issues detected")
    recommendations: List[str] = dspy.OutputField(desc="Suggested actions")
    report: str = dspy.OutputField(desc="Human-readable diagnostic report")


class DiagnoseSignature(dspy.Signature):
    """Diagnose a specific system problem and suggest solutions."""

    problem_description: str = dspy.InputField(desc="Description of the issue")
    system_state: str = dspy.InputField(desc="Current system state")
    recent_errors: str = dspy.InputField(desc="Recent error messages")

    root_cause: str = dspy.OutputField(desc="Identified root cause")
    severity: Literal["low", "medium", "high", "critical"] = dspy.OutputField()
    solution_steps: List[str] = dspy.OutputField(desc="Steps to resolve the issue")


# ============================================================
#  Multimodal Signatures
# ============================================================

class ImageUnderstandingSignature(dspy.Signature):
    """Understand and describe image content."""

    image_data: str = dspy.InputField(desc="Base64 encoded image or image URL")
    user_question: str = dspy.InputField(desc="What the user wants to know about the image")

    description: str = dspy.OutputField(desc="Description of image content")
    answer: str = dspy.OutputField(desc="Answer to user's question about the image")


class ASRProcessingSignature(dspy.Signature):
    """Process speech-to-text output and determine intent."""

    transcript: str = dspy.InputField(desc="Speech recognition transcript")
    conversation_context: str = dspy.InputField(desc="Recent conversation history")

    cleaned_text: str = dspy.OutputField(desc="Cleaned and formatted text")
    intent: str = dspy.OutputField(desc="Detected user intent")
    confidence: float = dspy.OutputField(desc="Confidence level (0.0-1.0)")


# ============================================================
#  Web Search Signatures
# ============================================================

class WebSearchSignature(dspy.Signature):
    """Formulate search queries and synthesize results."""

    user_question: str = dspy.InputField(desc="What the user wants to know")
    search_engine: str = dspy.InputField(desc="Which search engine to use")

    search_queries: List[str] = dspy.OutputField(desc="Optimized search queries")
    synthesized_answer: str = dspy.OutputField(desc="Answer synthesized from results")
    sources: List[str] = dspy.OutputField(desc="Sources used for the answer")


# ============================================================
#  Tool Creation Signature (Self-Evolution)
# ============================================================

class ToolCreationSignature(dspy.Signature):
    """Generate a new tool implementation based on requirements."""

    tool_name: str = dspy.InputField(desc="Name for the new tool")
    tool_description: str = dspy.InputField(desc="What the tool should do")
    required_parameters: str = dspy.InputField(desc="Parameters the tool needs")
    example_use_cases: str = dspy.InputField(desc="Example use cases for the tool")

    tool_code: str = dspy.OutputField(desc="Complete Python code for the tool")
    tool_schema: Dict[str, Any] = dspy.OutputField(desc="OpenAI-compatible tool schema")
