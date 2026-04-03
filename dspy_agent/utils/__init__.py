"""
DSPy Agent Utilities

This module provides utility functions for:
- LM configuration
- Teleprompter optimization
"""

import dspy
import json
import logging
from typing import Dict, List, Any, Callable

log = logging.getLogger("dspy_agent")


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
    from dspy_agent.modules import configure_lm
    configure_lm(config)

    return config


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

    log.info(f"[optimize] Starting {auto} optimization with {len(dspy_trainset)} examples...")

    optimized = teleprompter.compile(
        agent.deepcopy(),
        trainset=dspy_trainset,
        max_bootstrapped_demos=max_bootstrapped_demos,
        max_labeled_demos=max_labeled_demos,
    )

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
