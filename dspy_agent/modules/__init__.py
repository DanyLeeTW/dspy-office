"""
DSPy Modules for AI Agent

This module provides the core DSPy modules that replace the original llm.py functionality.

Key Components:
- Agent: Base DSPy module for conversation
- ToolAgent: ReAct-style agent with tool support
- MemoryModule: RAG-based memory retrieval
- ScheduledAgent: Agent for scheduled task execution

Migration from llm.py:
    # Old (llm.py)
    reply = llm.chat(user_msg, session_key, images=images)

    # New (dspy_agent/modules.py)
    agent = ToolAgent(tools=registry.get_tools())
    result = agent(user_request=user_msg, session_key=session_key)
"""

import dspy
import json
import os
import logging
import threading
import time
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime, timezone, timedelta

from ..signatures import (
    AgentSignature,
    ToolSelectionSignature,
    ToolExecutionSignature,
    MemoryCompressionSignature,
    MemoryRetrievalSignature,
    MemorySynthesisSignature,
    ScheduledTaskExecutionSignature,
)

log = logging.getLogger("dspy_agent")
CST = timezone(timedelta(hours=8))


# ============================================================
#  Configuration
# ============================================================

def configure_lm(config: Dict[str, Any]) -> None:
    """
    Configure DSPy language model from config.

    Args:
        config: Configuration dict with 'models' key containing providers

    Example:
        config = {
            "models": {
                "default": "deepseek-chat",
                "providers": {
                    "deepseek-chat": {
                        "api_base": "https://api.deepseek.com/v1",
                        "api_key": "...",
                        "model": "deepseek-chat",
                        "max_tokens": 8192
                    }
                }
            }
        }
        configure_lm(config)
    """
    models_config = config.get("models", {})
    default_name = models_config.get("default", "")

    providers = models_config.get("providers", {})
    provider = providers.get(default_name, {})

    if not provider:
        raise ValueError(f"No provider found for default model: {default_name}")

    # DSPy uses OpenAI-compatible format
    # Format: "openai/model_name" or custom endpoint
    api_base = provider.get("api_base", "https://api.openai.com/v1")
    api_key = provider.get("api_key", "")
    model = provider.get("model", "gpt-4o-mini")
    max_tokens = provider.get("max_tokens", 8192)

    # Construct model string for DSPy
    # DSPy format: "provider/model" where provider can be openai, anthropic, etc.
    # For custom endpoints, we use openai/ prefix with custom base URL
    if "deepseek" in api_base.lower():
        model_str = f"openai/{model}"
    elif "openai" in api_base.lower():
        model_str = f"openai/{model}"
    else:
        # Generic OpenAI-compatible endpoint
        model_str = f"openai/{model}"

    lm = dspy.LM(
        model_str,
        api_key=api_key,
        api_base=api_base,
        max_tokens=max_tokens,
    )

    dspy.configure(lm=lm)
    log.info(f"[dspy] Configured LM: {model_str} (base: {api_base})")


# ============================================================
#  Session Management (ported from llm.py)
# ============================================================

class SessionManager:
    """
    Manage conversation sessions with file-based persistence.

    Ported from llm.py to work with DSPy modules.
    """

    def __init__(self, sessions_dir: str, max_messages: int = 40):
        self.sessions_dir = sessions_dir
        self.max_messages = max_messages
        self._locks = {}
        self._locks_lock = threading.Lock()

        os.makedirs(sessions_dir, exist_ok=True)

    def _get_lock(self, session_key: str) -> threading.Lock:
        with self._locks_lock:
            if session_key not in self._locks:
                self._locks[session_key] = threading.Lock()
            return self._locks[session_key]

    def _session_path(self, session_key: str) -> str:
        safe = session_key.replace("/", "_").replace(":", "_").replace("\\", "_")
        return os.path.join(self.sessions_dir, f"{safe}.json")

    def load(self, session_key: str) -> List[Dict]:
        """Load session messages from file."""
        path = self._session_path(session_key)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    messages = json.load(f)

                # Truncate if needed and compress evicted
                if len(messages) > self.max_messages:
                    evicted = messages[:-self.max_messages]
                    messages = messages[-self.max_messages:]
                    self._compress_evicted(evicted, session_key)

                # Skip orphan tool messages at start
                while messages and messages[0].get("role") not in ("user", "system"):
                    messages.pop(0)

                return messages
            except Exception:
                return []
        return []

    def save(self, session_key: str, messages: List[Dict]) -> None:
        """Save session messages to file."""
        path = self._session_path(session_key)

        # Truncate if needed
        if len(messages) > self.max_messages:
            evicted = messages[:-self.max_messages]
            messages = messages[-self.max_messages:]
            self._compress_evicted(evicted, session_key)

        # Strip images for storage
        messages = self._strip_images(messages)

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False, indent=None)
        except Exception as e:
            log.error(f"[session] save error: {e}")

    def _strip_images(self, messages: List[Dict]) -> List[Dict]:
        """Replace image_url content with [image] markers for storage."""
        cleaned = []
        for msg in messages:
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                text_parts = []
                for item in msg["content"]:
                    if item.get("type") == "text":
                        text_parts.append(item["text"])
                    elif item.get("type") == "image_url":
                        text_parts.append("[image]")
                cleaned.append({"role": "user", "content": "\n".join(text_parts)})
            else:
                cleaned.append(msg)
        return cleaned

    def _compress_evicted(self, messages: List[Dict], session_key: str) -> None:
        """Compress evicted messages into long-term memory (async)."""
        if len(messages) < 2:
            return
        try:
            import memory as mem_mod
            mem_mod.compress_async(messages, session_key)
        except Exception as e:
            log.error(f"[session] compress error: {e}")

    def chat_thread_safe(self, session_key: str, chat_fn: Callable, *args, **kwargs):
        """Execute chat function with session lock."""
        lock = self._get_lock(session_key)
        with lock:
            return chat_fn(*args, **kwargs)


# ============================================================
#  Base Agent Module
# ============================================================

class Agent(dspy.Module):
    """
    Base DSPy Agent module for conversation.

    This replaces the core llm.chat() functionality with DSPy's Predict.
    Use this for simple Q&A without tool calling.

    For tool support, use ToolAgent instead.

    Usage:
        agent = Agent()
        result = agent(
            user_request="What is the weather?",
            conversation_history="...",
            available_tools="",
            memory_context=""
        )
        print(result.response)
    """

    def __init__(self, use_chain_of_thought: bool = True):
        super().__init__()
        if use_chain_of_thought:
            self.predict = dspy.ChainOfThought(AgentSignature)
        else:
            self.predict = dspy.Predict(AgentSignature)

    def forward(
        self,
        user_request: str,
        conversation_history: str = "",
        available_tools: str = "",
        memory_context: str = ""
    ) -> dspy.Prediction:
        """Process user request and generate response."""
        return self.predict(
            user_request=user_request,
            conversation_history=conversation_history,
            available_tools=available_tools,
            memory_context=memory_context
        )


# ============================================================
#  Tool Agent Module (ReAct-style)
# ============================================================

class ToolAgent(dspy.Module):
    """
    DSPy ReAct-style agent with tool support.

    This is the main replacement for the original llm.py chat loop.
    Uses DSPy's built-in ReAct for tool orchestration.

    Key differences from original llm.py:
    1. Uses dspy.ReAct instead of manual tool loop
    2. Tools are plain Python functions
    3. Automatic reasoning trace via trajectory
    4. Built-in max_iters handling

    Usage:
        from dspy_agent.tools import registry

        agent = ToolAgent(
            signature="user_request -> response",
            tools=registry.get_tools(),
            max_iters=20
        )

        result = agent(user_request="What's the weather in Tokyo?")
        print(result.response)
        print(result.trajectory)  # Reasoning steps
    """

    def __init__(
        self,
        signature: str = "user_request -> response",
        tools: List[Callable] = None,
        max_iters: int = 20,
        use_chain_of_thought: bool = True
    ):
        super().__init__()
        self.tools = tools or []
        self.max_iters = max_iters

        # Build signature with instructions
        instructions = """You are a helpful AI assistant that uses tools to help users.

        Analyze the user's request carefully and select the most appropriate tool.
        If no tool is needed, respond directly to the user.
        Be concise and helpful in your responses.
        """

        # Create a proper signature class
        class ToolAgentSignature(dspy.Signature):
            """You are a helpful AI assistant that uses tools to help users.
            Analyze the user's request carefully and select the most appropriate tool.
            If no tool is needed, respond directly to the user.
            """
            user_request: str = dspy.InputField(desc="The user's message or request")
            response: str = dspy.OutputField(desc="Your response to the user")

        # Use DSPy's ReAct for tool orchestration
        self.react = dspy.ReAct(
            ToolAgentSignature,
            tools=self.tools,
            max_iters=self.max_iters
        )

    def forward(self, user_request: str) -> dspy.Prediction:
        """Process user request with tool support."""
        return self.react(user_request=user_request)


# ============================================================
#  Memory Module (RAG-style)
# ============================================================

class MemoryModule(dspy.Module):
    """
    DSPy module for memory retrieval and synthesis.

    Replaces the memory retrieval logic from llm.py with DSPy's RAG pattern.

    This module:
    1. Takes a user query
    2. Generates search keywords
    3. Retrieves relevant memories from LanceDB
    4. Synthesizes into context for the main agent

    Usage:
        memory = MemoryModule(retrieve_fn=mem_mod.retrieve)
        context = memory(query="What did we discuss about Python?")
        # context.memory_context can be injected into Agent
    """

    def __init__(
        self,
        retrieve_fn: Callable = None,
        use_chain_of_thought: bool = True
    ):
        super().__init__()
        self.retrieve_fn = retrieve_fn

        if use_chain_of_thought:
            self.retrieval = dspy.ChainOfThought(MemoryRetrievalSignature)
            self.synthesis = dspy.ChainOfThought(MemorySynthesisSignature)
        else:
            self.retrieval = dspy.Predict(MemoryRetrievalSignature)
            self.synthesis = dspy.Predict(MemorySynthesisSignature)

    def forward(
        self,
        query: str,
        conversation_context: str = "",
        session_key: str = ""
    ) -> dspy.Prediction:
        """Retrieve and synthesize relevant memories."""

        # Step 1: Determine search keywords
        retrieval_result = self.retrieval(
            query=query,
            conversation_context=conversation_context
        )

        # Step 2: Retrieve from vector store
        if self.retrieve_fn:
            try:
                raw_memories = self.retrieve_fn(
                    " ".join(retrieval_result.search_keywords),
                    session_key
                )
            except Exception as e:
                log.error(f"[memory] retrieve error: {e}")
                raw_memories = ""
        else:
            raw_memories = ""

        # Step 3: Synthesize into context
        synthesis_result = self.synthesis(
            user_query=query,
            retrieved_memories=raw_memories or "No relevant memories found."
        )

        return dspy.Prediction(
            memory_context=synthesis_result.memory_context,
            search_keywords=retrieval_result.search_keywords,
            raw_memories=raw_memories
        )


# ============================================================
#  Memory Compression Module
# ============================================================

class MemoryCompressor(dspy.Module):
    """
    DSPy module for compressing conversation into long-term memories.

    Replaces the LLM-based compression in memory.py with DSPy module.

    Usage:
        compressor = MemoryCompressor()
        memories = compressor(conversation="User: I like Python\\nAssistant: ...")
        # memories.memories is a list of extracted facts
    """

    def __init__(self, use_chain_of_thought: bool = True):
        super().__init__()
        if use_chain_of_thought:
            self.compress = dspy.ChainOfThought(MemoryCompressionSignature)
        else:
            self.compress = dspy.Predict(MemoryCompressionSignature)

    def forward(self, conversation: str) -> dspy.Prediction:
        """Extract structured memories from conversation."""
        return self.compress(conversation=conversation)


# ============================================================
#  Scheduled Agent Module
# ============================================================

class ScheduledAgent(dspy.Module):
    """
    DSPy module for executing scheduled tasks.

    Replaces the scheduler's LLM calls with DSPy module.

    Usage:
        agent = ScheduledAgent()
        result = agent(
            task_name="daily-self-check",
            task_message="Run self_check and send report",
            current_context="System is healthy"
        )
        print(result.response)
    """

    def __init__(self, use_chain_of_thought: bool = True):
        super().__init__()
        if use_chain_of_thought:
            self.execute = dspy.ChainOfThought(ScheduledTaskExecutionSignature)
        else:
            self.execute = dspy.Predict(ScheduledTaskExecutionSignature)

    def forward(
        self,
        task_name: str,
        task_message: str,
        current_context: str = ""
    ) -> dspy.Prediction:
        """Execute a scheduled task."""
        return self.execute(
            task_name=task_name,
            task_message=task_message,
            current_context=current_context
        )


# ============================================================
#  Complete Agent Pipeline
# ============================================================

class CompleteAgent(dspy.Module):
    """
    Complete agent pipeline with memory and tools.

    This is the full replacement for llm.chat() that combines:
    1. Memory retrieval
    2. Tool-based reasoning
    3. Response generation

    Usage:
        from dspy_agent.tools import registry

        agent = CompleteAgent(
            tools=registry.get_tools(),
            retrieve_fn=mem_mod.retrieve,
            max_iters=20
        )

        result = agent(
            user_request="What's the weather?",
            session_key="dm_12345"
        )
        print(result.response)
    """

    def __init__(
        self,
        tools: List[Callable] = None,
        retrieve_fn: Callable = None,
        max_iters: int = 20,
        use_chain_of_thought: bool = True
    ):
        super().__init__()

        self.memory = MemoryModule(retrieve_fn, use_chain_of_thought)

        # Build the main agent signature
        class CompleteAgentSignature(dspy.Signature):
            """You are a helpful AI assistant with access to tools and memory.

            Use tools when necessary to accomplish tasks.
            Consider relevant memories when responding.
            Be concise and helpful.
            """
            user_request: str = dspy.InputField(desc="The user's message or request")
            conversation_history: str = dspy.InputField(desc="Previous conversation context")
            memory_context: str = dspy.InputField(desc="Relevant memories from long-term storage")
            response: str = dspy.OutputField(desc="Your response to the user")

        self.agent = dspy.ReAct(
            CompleteAgentSignature,
            tools=tools or [],
            max_iters=max_iters
        )

    def forward(
        self,
        user_request: str,
        conversation_history: str = "",
        session_key: str = ""
    ) -> dspy.Prediction:
        """Process user request with memory and tools."""

        # Step 1: Retrieve relevant memories
        memory_result = self.memory(
            query=user_request,
            conversation_context=conversation_history,
            session_key=session_key
        )

        # Step 2: Generate response with tools
        result = self.agent(
            user_request=user_request,
            conversation_history=conversation_history,
            memory_context=memory_result.memory_context
        )

        return dspy.Prediction(
            response=result.response,
            trajectory=result.trajectory,
            memory_context=memory_result.memory_context
        )


# ============================================================
#  Utility Functions
# ============================================================

def build_system_prompt(workspace: str) -> str:
    """Build system prompt from workspace files (ported from llm.py)."""
    now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S CST")
    parts = [f"You are the user's private AI assistant.\nCurrent time: {now_str}\n"]

    for filename in ["SOUL.md", "AGENT.md", "USER.md"]:
        fpath = os.path.join(workspace, filename)
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    parts.append(f.read())
            except Exception:
                pass

    return "\n\n---\n\n".join(parts)


def format_conversation_history(messages: List[Dict]) -> str:
    """Format message list into conversation text for DSPy."""
    lines = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user":
            lines.append(f"User: {content}")
        elif role == "assistant":
            # Include tool calls in history
            if msg.get("tool_calls"):
                tool_names = [tc["function"]["name"] for tc in msg["tool_calls"]]
                lines.append(f"Assistant: [Called tools: {', '.join(tool_names)}] {content}")
            else:
                lines.append(f"Assistant: {content}")
        elif role == "tool":
            lines.append(f"Tool result: {content[:200]}...")

    return "\n".join(lines)
