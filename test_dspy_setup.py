#!/usr/bin/env python3.12
"""
DSPy Agent Configuration Test

This script tests the DSPy configuration with Tencent Coding GLM-5 API.

Usage:
    python3 test_dspy_setup.py
"""

import os
import sys
import json

# Ensure we're in the correct directory
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(DATA_DIR)

# Load configuration
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

print("=" * 60)
print("DSPy Agent Configuration Test")
print("=" * 60)

# Step 1: Load config
print("\n[1/4] Loading configuration...")
try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    print(f"  ✅ Config loaded from: {CONFIG_PATH}")
    print(f"  - Default model: {config['models']['default']}")
    print(f"  - API base: {config['models']['providers']['glm-5']['api_base']}")
    print(f"  - Model: {config['models']['providers']['glm-5']['model']}")
    print(f"  - Max tokens: {config['models']['providers']['glm-5']['max_tokens']}")
except Exception as e:
    print(f"  ❌ Failed to load config: {e}")
    sys.exit(1)

# Step 2: Install DSPy if needed
print("\n[2/4] Checking DSPy installation...")
try:
    import dspy
    print(f"  ✅ DSPy version: {dspy.__version__ if hasattr(dspy, '__version__') else 'installed'}")
except ImportError:
    print("  ⚠️ DSPy not installed. Installing...")
    os.system("pip install dspy")
    import dspy
    print("  ✅ DSPy installed")

# Step 3: Configure LM
print("\n[3/4] Configuring DSPy LM...")
try:
    from dspy_agent.modules import configure_lm
    configure_lm(config)
    print("  ✅ DSPy LM configured successfully")
except Exception as e:
    print(f"  ❌ Failed to configure LM: {e}")
    sys.exit(1)

# Step 4: Test a simple query
print("\n[4/4] Testing GLM-5 API connection...")
try:
    # Simple test using DSPy Predict
    class TestSignature(dspy.Signature):
        """Answer a simple question."""
        question: str = dspy.InputField()
        answer: str = dspy.OutputField()

    predictor = dspy.Predict(TestSignature)
    result = predictor(question="Say 'Hello, DSPy!' in exactly those words.")

    print(f"  ✅ API call successful!")
    print(f"  Response: {result.answer[:100]}...")
except Exception as e:
    print(f"  ❌ API test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ All tests passed! DSPy Agent is ready to use.")
print("=" * 60)
print("\nTo start the agent:")
print("  python3 dspy_xiaowang.py")
