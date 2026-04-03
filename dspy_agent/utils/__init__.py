"""
DSPy Agent Utilities

This module provides utility functions for:
- LM configuration
- Teleprompter optimization
- Evaluation metrics
- Helper functions
"""

import dspy
import json
import logging
import os
from typing import Dict, List, Any, Callable, Optional
from datetime import datetime, timezone, timedelta

log = logging.getLogger("dspy_agent")
CST = timezone(timedelta(hours=8))


# ============================================================
#  Configuration Utilities
# ============================================================

def configure_from_file(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from JSON file and configure DSPy.

    Args:
        config_path: Path to config.json

    Returns:
        Loaded configuration dict
    """
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # Configure DSPy LM
    from .modules import configure_lm
    configure_lm(config)

    return config


def configure_from_env() -> Dict[str, Any]:
    """
    Configure DSPy from environment variables.

    Environment variables:
        DSPY_MODEL: Model name (e.g., "openai/gpt-4o-mini")
        DSPY_API_KEY: API key
        DSPY_API_BASE: API base URL (optional)

    Returns:
        Configuration dict
    """
    model = os.environ.get("DSPY_MODEL", "openai/gpt-4o-mini")
    api_key = os.environ.get("DSPY_API_KEY", "")
    api_base = os.environ.get("DSPY_API_BASE", None)

    lm = dspy.LM(model, api_key=api_key)
    if api_base:
        lm.api_base = api_base

    dspy.configure(lm=lm)

    return {
        "model": model,
        "api_key": api_key,
        "api_base": api_base
    }


# ============================================================
#  Optimization (Teleprompter) Utilities
# ============================================================

def optimize_agent(
    agent: dspy.Module,
    trainset: List[Dict],
    metric: Callable = None,
    auto: str = "light",
    max_bootstrapped_demos: int = 3,
    max_labeled_demos: int = 4,
    save_path: str = None
) -> dspy.Module:
    """
    Optimize a DSPy agent using MIPROv2 teleprompter.

    Args:
        agent: DSPy module to optimize
        trainset: Training examples (list of dicts with inputs and expected outputs)
        metric: Evaluation metric function (signature: (gold, pred) -> bool)
        auto: Optimization level: "light", "medium", or "heavy"
        max_bootstrapped_demos: Max bootstrapped demonstrations
        max_labeled_demos: Max labeled demonstrations
        save_path: Path to save optimized program (optional)

    Returns:
        Optimized agent

    Example:
        def my_metric(gold, pred):
            return gold.answer.lower() == pred.response.lower()

        trainset = [
            {"user_request": "Hello", "response": "Hi there!"},
            {"user_request": "Goodbye", "response": "See you later!"},
        ]

        optimized = optimize_agent(agent, trainset, metric=my_metric)
    """
    from dspy.teleprompt import MIPROv2

    # Default metric: check if response is non-empty
    if metric is None:
        def default_metric(gold, pred):
            return bool(pred.response and len(pred.response.strip()) > 0)
        metric = default_metric

    # Convert trainset to DSPy Examples
    dspy_trainset = []
    for example in trainset:
        dspy_example = dspy.Example(**example).with_inputs(
            *[k for k in example.keys() if k not in ["response", "answer"]]
        )
        dspy_trainset.append(dspy_example)

    # Initialize optimizer
    teleprompter = MIPROv2(
        metric=metric,
        auto=auto,
        num_threads=4
    )

    # Compile optimized program
    log.info(f"[optimize] Starting {auto} optimization with {len(dspy_trainset)} examples...")

    optimized = teleprompter.compile(
        agent.deepcopy(),
        trainset=dspy_trainset,
        max_bootstrapped_demos=max_bootstrapped_demos,
        max_labeled_demos=max_labeled_demos,
    )

    # Save if path provided
    if save_path:
        optimized.save(save_path)
        log.info(f"[optimize] Saved optimized program to {save_path}")

    return optimized


def load_optimized_agent(agent_class, path: str) -> dspy.Module:
    """
    Load an optimized agent from saved state.

    Args:
        agent_class: The agent class (e.g., ToolAgent)
        path: Path to saved optimization state

    Returns:
        Loaded agent with optimized parameters
    """
    agent = agent_class()
    agent.load(path)
    return agent


# ============================================================
#  Evaluation Metrics
# ============================================================

def exact_match_metric(gold: dspy.Example, pred: dspy.Prediction) -> bool:
    """Check if predicted response exactly matches expected."""
    expected = getattr(gold, "response", getattr(gold, "answer", ""))
    return expected.lower().strip() == pred.response.lower().strip()


def contains_metric(gold: dspy.Example, pred: dspy.Prediction) -> bool:
    """Check if predicted response contains expected keywords."""
    expected = getattr(gold, "response", getattr(gold, "answer", ""))
    return expected.lower() in pred.response.lower()


def tool_usage_metric(expected_tools: List[str]) -> Callable:
    """
    Create a metric that checks if expected tools were used.

    Args:
        expected_tools: List of tool names that should be called

    Returns:
        Metric function

    Usage:
        metric = tool_usage_metric(["web_search", "read_file"])
        # Returns True if both tools were called in trajectory
    """
    def metric(gold: dspy.Example, pred: dspy.Prediction) -> bool:
        if not hasattr(pred, "trajectory"):
            return False

        used_tools = set()
        for step in pred.trajectory:
            if hasattr(step, "tool_name"):
                used_tools.add(step.tool_name)

        return all(tool in used_tools for tool in expected_tools)

    return metric


def response_quality_metric(gold: dspy.Example, pred: dspy.Prediction) -> float:
    """
    Evaluate response quality on a scale of 0-1.

    Checks:
    - Response exists (0.2 points)
    - Non-trivial length (0.2 points)
    - No error messages (0.2 points)
    - Contains expected content (0.4 points)
    """
    score = 0.0

    # Response exists
    if pred.response:
        score += 0.2

    # Non-trivial length (> 20 chars)
    if len(pred.response.strip()) > 20:
        score += 0.2

    # No error messages
    if "[error]" not in pred.response.lower():
        score += 0.2

    # Contains expected content
    expected = getattr(gold, "response", getattr(gold, "answer", ""))
    if expected and expected.lower() in pred.response.lower():
        score += 0.4

    return score


# ============================================================
#  Helper Functions
# ============================================================

def create_dspy_example(
    user_request: str,
    response: str,
    conversation_history: str = "",
    memory_context: str = ""
) -> dspy.Example:
    """
    Create a DSPy Example for training.

    Args:
        user_request: The user's input
        response: Expected response
        conversation_history: Previous context
        memory_context: Memory context

    Returns:
        DSPy Example with inputs marked
    """
    return dspy.Example(
        user_request=user_request,
        conversation_history=conversation_history,
        memory_context=memory_context,
        response=response
    ).with_inputs("user_request", "conversation_history", "memory_context")


def batch_process(
    agent: dspy.Module,
    requests: List[str],
    session_keys: List[str] = None
) -> List[dspy.Prediction]:
    """
    Process multiple requests in batch.

    Args:
        agent: DSPy agent module
        requests: List of user requests
        session_keys: Optional session keys for each request

    Returns:
        List of predictions
    """
    results = []

    for i, request in enumerate(requests):
        session_key = session_keys[i] if session_keys else f"batch_{i}"
        try:
            result = agent(user_request=request, session_key=session_key)
            results.append(result)
        except Exception as e:
            log.error(f"[batch] Error processing request {i}: {e}")
            results.append(dspy.Prediction(response=f"[error] {e}"))

    return results


def format_trajectory(trajectory: List) -> str:
    """
    Format agent trajectory for display.

    Args:
        trajectory: List of reasoning steps

    Returns:
        Formatted string
    """
    lines = ["=== Agent Trajectory ==="]

    for i, step in enumerate(trajectory, 1):
        lines.append(f"\nStep {i}:")

        if hasattr(step, "thought"):
            lines.append(f"  Thought: {step.thought}")

        if hasattr(step, "tool_name"):
            lines.append(f"  Tool: {step.tool_name}")

        if hasattr(step, "tool_args"):
            args_str = json.dumps(step.tool_args, ensure_ascii=False)
            lines.append(f"  Args: {args_str[:100]}...")

        if hasattr(step, "tool_result"):
            lines.append(f"  Result: {str(step.tool_result)[:100]}...")

    return "\n".join(lines)


def get_agent_stats(agent: dspy.Module) -> Dict[str, Any]:
    """
    Get statistics about a DSPy agent.

    Args:
        agent: DSPy module

    Returns:
        Dict with stats
    """
    stats = {
        "module_type": type(agent).__name__,
        "num_parameters": 0,
        "sub_modules": []
    }

    # Count sub-modules
    for name, module in agent.named_sub_modules():
        stats["sub_modules"].append({
            "name": name,
            "type": type(module).__name__
        })

    return stats


# ============================================================
#  Migration Helpers
# ============================================================

def convert_legacy_session(session_path: str) -> List[dspy.Example]:
    """
    Convert legacy session file to DSPy Examples.

    Args:
        session_path: Path to legacy session JSON file

    Returns:
        List of DSPy Examples
    """
    with open(session_path, "r", encoding="utf-8") as f:
        messages = json.load(f)

    examples = []
    current_request = ""
    current_history = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user":
            if current_request and current_history:
                # Save previous turn
                examples.append(create_dspy_example(
                    user_request=current_request,
                    response="",  # Will be filled from next assistant message
                    conversation_history="\n".join(current_history)
                ))
            current_request = content
        elif role == "assistant":
            if current_request and examples:
                # Fill in response for last example
                examples[-1] = create_dspy_example(
                    user_request=current_request,
                    response=content,
                    conversation_history="\n".join(current_history)
                )
                current_history.append(f"User: {current_request}")
                current_history.append(f"Assistant: {content}")
                current_request = ""

    return examples


def estimate_token_count(text: str) -> int:
    """
    Estimate token count for a string.

    Rough approximation: 4 characters per token for English, 2 for Chinese.
    """
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars

    return chinese_chars // 2 + other_chars // 4
