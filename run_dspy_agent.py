#!/usr/bin/env python3.12
"""
DSPy Agent - Simple Launcher

A simplified launcher for the DSPy Agent that starts the HTTP server.

Usage:
    python3.12 run_dspy_agent.py
"""

import sys
import os

# Ensure we're in the correct directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

# Configuration
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'config.json')
SESSIONS_DIR = os.path.join(SCRIPT_DIR, 'sessions')
MEMORY_DB = os.path.join(SCRIPT_DIR, 'memory_db')

# Create directories
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(MEMORY_DB, exist_ok=True)

print("=" * 50)
print("DSPy Agent Launcher")
print("=" * 50)

# Load config
import json
with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

print(f"Model: {config['models']['default']}")

# Step 1: Configure DSPy
print("\n[1/6] Configuring DSPy...")
from dspy_agent.utils import configure_from_file
configure_from_file(CONFIG_PATH)

# Step 2: Initialize messaging
print("[2/6] Initializing messaging...")
import messaging
messaging.init(config.get('messaging', {}))

# Step 3: Initialize session manager
print("[3/6] Initializing session manager...")
from dspy_agent.modules import SessionManager
session_manager = SessionManager(SESSIONS_DIR)

# Step 4: Initialize memory (optional)
print("[4/6] Initializing memory system...")
try:
    import memory as mem_mod
    mem_mod.init(config, config.get('models', {}), MEMORY_DB)
    retrieve_fn = mem_mod.retrieve
except Exception as e:
    print(f"      Warning: Memory disabled ({e})")
    retrieve_fn = None

# Step 5: Initialize tools and agent
print("[5/6] Creating DSPy agent...")
from dspy_agent.modules import CompleteAgent
from dspy_agent.tools import registry, get_all_tools

registry._workspace = config.get('workspace', './workspace')
registry._owner_id = next(iter(config.get('owner_ids', [])), "")

agent = CompleteAgent(
    tools=get_all_tools(),
    retrieve_fn=retrieve_fn,
    max_iters=10
)

# Step 6: Start HTTP server
print("[6/6] Starting HTTP server...")
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import threading
import time

PORT = config.get('port', 8080)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "ok",
            "service": "dspy-agent",
            "model": config['models']['default']
        }).encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"")

        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            return

        # Test endpoint
        if self.path == "/test":
            msg = data.get("message", "")
            if msg:
                def _test():
                    try:
                        result = agent(user_request=msg, conversation_history="", session_key="test")
                        print(f"[test] Response: {result.response[:100]}...")
                    except Exception as e:
                        print(f"[test] Error: {e}")
                threading.Thread(target=_test, daemon=True).start()
            return

        # Chat endpoint
        if self.path == "/chat":
            msg = data.get("message", "")
            if msg:
                def _chat():
                    try:
                        result = agent(user_request=msg, conversation_history="", session_key="api")
                        print(f"[chat] Response: {result.response[:100]}...")
                    except Exception as e:
                        print(f"[chat] Error: {e}")
                threading.Thread(target=_chat, daemon=True).start()
            return

    def log_message(self, format, *args):
        pass


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


print("\n" + "=" * 50)
print(f"✅ DSPy Agent ready!")
print(f"   Port: {PORT}")
print(f"   Test: curl -X POST http://localhost:{PORT}/test -d '{{\"message\":\"Hello\"}}'")
print("=" * 50)

server = ThreadedHTTPServer(("0.0.0.0", PORT), Handler)
try:
    server.serve_forever()
except KeyboardInterrupt:
    print("\n[agent] Shutting down...")
    server.server_close()
