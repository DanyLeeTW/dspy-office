#!/usr/bin/env python3.12
"""
DSPy Agent - Entry Point

This is the DSPy-based version of the AI agent system.
It replaces the original xiaowang.py with DSPy modules while maintaining
backward compatibility with the messaging platform integration.

Key Differences from Original:
1. Uses DSPy modules instead of manual LLM API calls
2. Tools are plain functions compatible with dspy.ReAct
3. Built-in support for Teleprompter optimization
4. RAG-based memory retrieval

Usage:
    python3.12 dspy_xiaowang.py

Environment Variables:
    AGENT_CONFIG: Path to config.json (default: ./config.json)
    DSPY_OPTIMIZED: Path to optimized agent state (optional)
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import json
import logging
import os
import threading
import time

# ============================================================
#  Configuration
# ============================================================

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get("AGENT_CONFIG", os.path.join(DATA_DIR, "config.json"))

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

OWNER_IDS = set(str(x) for x in CONFIG.get("owner_ids", []))
WORKSPACE = os.path.abspath(CONFIG.get("workspace", "./workspace"))
PORT = CONFIG.get("port", 8080)
DEBOUNCE_SECONDS = CONFIG.get("debounce_seconds", 3.0)
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
FILES_DIR = os.path.join(WORKSPACE, "files")
OPTIMIZED_PATH = os.environ.get("DSPY_OPTIMIZED", None)

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("dspy_agent")

# ============================================================
#  Initialize DSPy
# ============================================================

# Configure DSPy language model
from dspy_agent.utils import configure_from_file, load_optimized_agent
from dspy_agent.modules import (
    CompleteAgent,
    SessionManager,
    build_system_prompt,
    format_conversation_history,
)
from dspy_agent.tools import registry, get_all_tools

log.info("[dspy] Configuring language model...")
configure_from_file(CONFIG_PATH)

# Initialize messaging (still using original module)
import messaging
messaging.init(CONFIG["messaging"])

# Initialize llm module for fallback
import llm
llm.init(CONFIG["models"], WORKSPACE, next(iter(OWNER_IDS), ""), SESSIONS_DIR)

# Initialize session manager
session_manager = SessionManager(SESSIONS_DIR)

# Initialize memory system
import memory as mem_mod
_mem_db = os.path.join(DATA_DIR, 'memory_db')
os.makedirs(_mem_db, exist_ok=True)
mem_mod.init(CONFIG, CONFIG.get('models', {}), _mem_db)

# Initialize scheduler
import scheduler
scheduler.init(os.path.join(DATA_DIR, "jobs.json"), None)  # Will set chat_fn later

# Initialize tools with config
registry._workspace = WORKSPACE
registry._owner_id = next(iter(OWNER_IDS), "")

# Initialize agent
log.info("[dspy] Initializing agent...")
if OPTIMIZED_PATH and os.path.exists(OPTIMIZED_PATH):
    log.info(f"[dspy] Loading optimized agent from {OPTIMIZED_PATH}")
    agent = load_optimized_agent(CompleteAgent, OPTIMIZED_PATH)
else:
    agent = CompleteAgent(
        tools=get_all_tools(),
        retrieve_fn=None,  # Disable memory retrieval temporarily
        max_iters=20,
        use_chain_of_thought=False  # Disable for GLM-5 compatibility
    )

# Set scheduler chat function
def dspy_chat_fn(message: str, session_key: str) -> str:
    """Chat function for scheduler using DSPy agent."""
    try:
        result = agent(
            user_request=message,
            conversation_history="",
            session_key=session_key
        )
        return result.response
    except Exception as e:
        log.error(f"[dspy_chat] Error: {e}", exc_info=True)
        return f"Error: {e}"

scheduler._chat_fn = dspy_chat_fn


# ============================================================
#  Debounce (ported from xiaowang.py)
# ============================================================

_debounce_buffers = {}
_debounce_timers = {}
_debounce_lock = threading.Lock()


def _debounce_flush(sender_id):
    with _debounce_lock:
        fragments = _debounce_buffers.pop(sender_id, [])
        _debounce_timers.pop(sender_id, None)

    if not fragments:
        return

    texts = []
    images = []
    for frag in fragments:
        if isinstance(frag, dict):
            if frag.get("text"):
                texts.append(frag["text"])
            images.extend(frag.get("images", []))
        else:
            texts.append(str(frag))

    combined_text = "\n".join(texts)
    if len(fragments) > 1:
        log.info(f"[debounce] {sender_id}: merged {len(fragments)} messages")

    try:
        if str(sender_id) not in OWNER_IDS:
            messaging.send_text(sender_id, "Sorry, this agent is currently in single-user mode.")
            return

        log.info(f"[chat] {sender_id} -> DSPy agent (images={len(images)})")
        session_key = f"dm_{sender_id}"

        # Load session
        messages = session_manager.load(session_key)

        # Format history
        history = format_conversation_history(messages)

        # Call DSPy agent
        result = agent(
            user_request=combined_text,
            conversation_history=history,
            session_key=session_key
        )

        reply = result.response

        # Save session
        messages.append({"role": "user", "content": combined_text})
        messages.append({"role": "assistant", "content": reply})
        session_manager.save(session_key, messages)

        if not reply or not reply.strip():
            log.warning(f"[chat] empty reply for {sender_id}")
            return

        # Send reply (split if needed)
        for i, chunk in enumerate(split_message(reply, 1800)):
            messaging.send_text(sender_id, chunk)
            if i > 0:
                time.sleep(0.5)

        # Log trajectory if available
        if hasattr(result, 'trajectory'):
            log.info(f"[chat] Tool calls: {len([s for s in result.trajectory if hasattr(s, 'tool_name')])}")

    except Exception as e:
        log.error(f"[flush] error for {sender_id}: {e}", exc_info=True)
        try:
            messaging.send_text(sender_id, f"Sorry, error processing message: {e}")
        except Exception:
            pass


def debounce_message(sender_id, text, images=None):
    with _debounce_lock:
        frag = {"text": text, "images": images or []}
        _debounce_buffers.setdefault(sender_id, []).append(frag)
        old_timer = _debounce_timers.get(sender_id)
        if old_timer:
            old_timer.cancel()
        timer = threading.Timer(DEBOUNCE_SECONDS, _debounce_flush, args=[sender_id])
        timer.daemon = True
        timer.start()
        _debounce_timers[sender_id] = timer
        count = len(_debounce_buffers[sender_id])
    log.info(f"[debounce] {sender_id}: buffered #{count}")


def split_message(text, max_bytes=1800):
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]
    chunks, current = [], ""
    for line in text.split("\n"):
        test = current + "\n" + line if current else line
        if len(test.encode("utf-8")) > max_bytes:
            if current:
                chunks.append(current)
            current = line
        else:
            current = test
    if current:
        chunks.append(current)
    return chunks


# ============================================================
#  Callback Handler
# ============================================================

def handle_callback(data):
    if isinstance(data, dict) and "testMsg" in data:
        log.info(f"[callback] test: {data['testMsg']}")
        return
    if not isinstance(data, dict):
        return

    messages = data.get("data", [])
    if isinstance(messages, dict):
        messages = [messages]
    elif not isinstance(messages, list):
        return

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        cmd = msg.get("cmd")
        sender_id = msg.get("senderId")
        msg_type = msg.get("msgType")
        msg_data = msg.get("msgData", {})
        if not isinstance(msg_data, dict):
            msg_data = {}

        # Skip messages sent by self
        if str(sender_id) == str(msg.get("userId")):
            continue

        if cmd == 15000:
            if msg_type in (0, 2):
                content = msg_data.get("content", "")
                if content:
                    log.info(f"[callback] text from {sender_id}: {content[:100]}")
                    debounce_message(sender_id, content)
            elif msg_type in (7, 14, 101):
                log.info(f"[callback] image from {sender_id}")
                # Handle image - would need media download logic
                debounce_message(sender_id, "[User sent an image]")
            elif msg_type in (22, 23, 103):
                log.info(f"[callback] video from {sender_id}")
                debounce_message(sender_id, "[User sent a video]")
            elif msg_type in (15, 20, 102):
                filename = msg_data.get("filename", msg_data.get("fileName", "unknown"))
                log.info(f"[callback] file from {sender_id}: {filename}")
                debounce_message(sender_id, f"[User sent a file: {filename}]")
            elif msg_type == 13:
                title = msg_data.get("title", "")
                url = msg_data.get("linkUrl", msg_data.get("url", ""))
                log.info(f"[callback] link from {sender_id}: {title}")
                debounce_message(sender_id, f"[User shared a link]\nTitle: {title}\nURL: {url}")


# ============================================================
#  HTTP Server
# ============================================================

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Handle /api/mcp-servers - return MCP server config
        if self.path == "/api/mcp-servers":
            mcp_servers = CONFIG.get("mcp_servers", {})
            servers_list = [
                {"name": name, **cfg}
                for name, cfg in mcp_servers.items()
            ]
            encoded = json.dumps({"mcp_servers": servers_list}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(encoded)
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "ok",
            "service": "dspy-agent",
            "version": "2.0.0"
        }).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        # Handle /api/chat - sync response for frontend
        if self.path == "/api/chat" or self.path == "/api/chat/stream":
            is_stream = self.path == "/api/chat/stream"

            def _send_json(status, payload):
                encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()
                self.wfile.write(encoded)

            def _send_sse_event(event_type: str, data: dict):
                """Send a single SSE event."""
                event = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                self.wfile.write(event.encode("utf-8"))
                self.wfile.flush()

            def _send_streaming_response():
                """Send headers for SSE streaming."""
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

            try:
                data = json.loads(body.decode("utf-8"))
                msg = data.get("message", "") or data.get("msg", "")
                if not msg:
                    raise ValueError("missing 'message' field")

                session_key = data.get("session_key", "frontend_session")
                context = data.get("context", "")

                # Format conversation history
                messages = session_manager.load(session_key)
                history = format_conversation_history(messages)

                # Add context if provided
                if context:
                    msg = f"{msg}\n\nContext:\n{context}"

                # Streaming mode - real-time tool updates
                if is_stream:
                    _send_streaming_response()

                    reply = ''
                    try:
                        # Emit thinking event
                        _send_sse_event("thinking", {"content": "Processing request..."})

                        # Define callbacks for streaming
                        def on_tool_start(tool_name, args):
                            _send_sse_event("tool_start", {
                                "tool": tool_name,
                                "args": args
                            })

                        def on_tool_end(tool_name, result):
                            _send_sse_event("tool_end", {
                                "tool": tool_name,
                                "result": str(result)[:500] if result else ''
                            })

                        # Create streaming agent with callbacks
                        from dspy_agent.modules import StreamingToolAgent
                        streaming_agent = StreamingToolAgent(
                            tools=get_all_tools(),
                            retrieve_fn=None,
                            max_iters=20,
                            on_tool_start=on_tool_start,
                            on_tool_end=on_tool_end
                        )

                        result = streaming_agent(
                            user_request=msg,
                            conversation_history=history,
                            session_key=session_key
                        )
                        reply = result.response
                        memory_context = result.memory_context if hasattr(result, 'memory_context') else ''

                        # Emit final response
                        _send_sse_event("response", {
                            "content": reply,
                            "memory_context": memory_context
                        })

                        _send_sse_event("done", {})

                    except Exception as agent_error:
                        log.warning(f"[api/chat/stream] Agent error: {agent_error}", exc_info=True)
                        _send_sse_event("error", {"message": str(agent_error)})

                    # Save session
                    if reply:
                        messages.append({"role": "user", "content": msg})
                        messages.append({"role": "assistant", "content": reply})
                        session_manager.save(session_key, messages)
                    return

                # Non-streaming mode (original behavior)
                try:
                    result = agent(
                        user_request=msg,
                        conversation_history=history,
                        session_key=session_key
                    )
                    reply = result.response

                    # Extract trajectory (tool calls) - DSPy format: {thought_0, tool_name_0, tool_args_0, observation_0, ...}
                    tool_calls = []
                    if hasattr(result, 'trajectory') and result.trajectory:
                        traj = result.trajectory
                        idx = 0
                        while f'tool_name_{idx}' in traj:
                            tool_calls.append({
                                "tool": traj.get(f'tool_name_{idx}', ''),
                                "args": traj.get(f'tool_args_{idx}', {}),
                                "thought": traj.get(f'thought_{idx}', ''),
                                "result": traj.get(f'observation_{idx}', '')[:500] if traj.get(f'observation_{idx}') else ''
                            })
                            idx += 1

                    memory_context = result.memory_context if hasattr(result, 'memory_context') else ''

                except Exception as agent_error:
                    log.warning(f"[api/chat] DSPy agent error, using fallback: {agent_error}")
                    # Fallback: use simple LLM call without DSPy modules
                    import llm as llm_mod
                    reply = llm_mod.chat(msg, session_key)
                    tool_calls = []
                    memory_context = ''

                # Save session
                messages.append({"role": "user", "content": msg})
                messages.append({"role": "assistant", "content": reply})
                session_manager.save(session_key, messages)

                _send_json(200, {
                    "response": reply,
                    "tool_calls": tool_calls,
                    "memory_context": memory_context
                })

            except Exception as e:
                log.error(f"[api/chat] error: {e}", exc_info=True)
                _send_json(400 if isinstance(e, ValueError) else 500, {"error": str(e)})
            return

        # Handle /api/parse/pdf - extract text from PDF and return it
        if self.path == "/api/parse/pdf":
            def _send_json(status, payload):
                encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(encoded)

            try:
                content_type = self.headers.get("Content-Type", "")
                boundary = None
                for part in content_type.split(";"):
                    part = part.strip()
                    if part.startswith("boundary="):
                        boundary = part[9:].strip('"')
                        break

                if not boundary:
                    _send_json(400, {"success": False, "error": "No boundary"})
                    return

                boundary_bytes = f"--{boundary}".encode()
                parts = body.split(boundary_bytes)
                file_content = None
                filename = "file.pdf"

                for part in parts[1:]:
                    if b"\r\n\r\n" in part:
                        headers_raw, content = part.split(b"\r\n\r\n", 1)
                        headers_text = headers_raw.decode("utf-8", errors="ignore")
                        if 'name="file"' in headers_text:
                            for line in headers_text.split("\r\n"):
                                if "filename=" in line:
                                    for seg in line.split(";"):
                                        seg = seg.strip()
                                        if seg.startswith("filename="):
                                            filename = seg[9:].strip('"')
                            file_content = content.rstrip(b"\r\n")

                if not file_content:
                    _send_json(400, {"success": False, "error": "No file provided"})
                    return

                import tempfile, os
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(file_content)
                    tmp_path = tmp.name

                try:
                    from dspy_agent.tools import _extract_pdf_text
                    text = _extract_pdf_text(tmp_path)
                    _send_json(200, {"success": True, "text": text, "filename": filename})
                finally:
                    os.unlink(tmp_path)

            except Exception as e:
                log.error(f"[api/parse/pdf] error: {e}", exc_info=True)
                _send_json(500, {"success": False, "error": str(e)})
            return

        # Handle /api/upload - upload file from URL
        if self.path == "/api/upload":
            def _send_json(status, payload):
                encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(encoded)

            try:
                data = json.loads(body.decode("utf-8"))
                url = data.get("url", "")
                filename = data.get("filename")

                if not url:
                    _send_json(400, {"success": False, "error": "URL is required"})
                    return

                # Use the upload_file tool
                from dspy_agent.tools import upload_file
                result = upload_file(url=url, filename=filename, workspace=WORKSPACE)

                if result.startswith("[error]"):
                    _send_json(400, {"success": False, "error": result[8:]})
                else:
                    # Parse result for path, type, size
                    lines = result.split("\n")
                    path = lines[0].replace("File uploaded: ", "") if lines else ""
                    type_info = ""
                    size_info = ""
                    for line in lines[1:]:
                        if line.startswith("Type:"):
                            type_info = line.replace("Type: ", "")
                        if line.startswith("Size:"):
                            size_info = line.replace("Size: ", "")

                    _send_json(200, {
                        "success": True,
                        "path": path,
                        "type": type_info,
                        "size": size_info
                    })
            except Exception as e:
                log.error(f"[api/upload] error: {e}", exc_info=True)
                _send_json(500, {"success": False, "error": str(e)})
            return

        # Handle /api/upload/file - upload file directly
        if self.path == "/api/upload/file":
            def _send_json(status, payload):
                encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(encoded)

            try:
                content_type = self.headers.get("Content-Type", "")
                if "multipart/form-data" not in content_type:
                    _send_json(400, {"success": False, "error": "Expected multipart/form-data"})
                    return

                # Extract boundary from content-type
                boundary = None
                for part in content_type.split(";"):
                    part = part.strip()
                    if part.startswith("boundary="):
                        boundary = part[9:].strip('"')
                        break

                if not boundary:
                    _send_json(400, {"success": False, "error": "No boundary in content-type"})
                    return

                # Read and parse multipart data
                from pathlib import Path
                boundary_bytes = f"--{boundary}".encode()
                end_boundary = f"--{boundary}--".encode()
                body_parts = body.split(boundary_bytes)

                filename = None
                file_content = None
                custom_filename = None

                for part in body_parts[1:]:  # Skip first empty part
                    if part.startswith(end_boundary) or part == b"--\r\n":
                        continue

                    # Split headers and content
                    if b"\r\n\r\n" in part:
                        headers_raw, content = part.split(b"\r\n\r\n", 1)
                        headers_text = headers_raw.decode("utf-8", errors="ignore")

                        # Check if this is the file field
                        if 'name="file"' in headers_text:
                            # Extract filename from Content-Disposition
                            for line in headers_text.split("\r\n"):
                                if "filename=" in line:
                                    for seg in line.split(";"):
                                        seg = seg.strip()
                                        if seg.startswith("filename="):
                                            filename = seg[9:].strip('"')
                                            break

                            # Remove trailing boundary markers
                            file_content = content.rstrip(b"\r\n")
                            if file_content.endswith(end_boundary):
                                file_content = file_content[:-len(end_boundary)].rstrip(b"\r\n")

                        # Check for custom filename field
                        elif 'name="filename"' in headers_text:
                            custom_filename = content.decode("utf-8").strip()
                            if custom_filename.endswith("--"):
                                custom_filename = custom_filename[:-2].strip()

                if not file_content:
                    _send_json(400, {"success": False, "error": "No file provided"})
                    return

                # Use custom filename if provided
                final_filename = custom_filename or filename
                if not final_filename:
                    _send_json(400, {"success": False, "error": "No filename provided"})
                    return

                # Save file to workspace
                file_path = Path(WORKSPACE) / final_filename
                file_path.parent.mkdir(parents=True, exist_ok=True)

                with open(file_path, "wb") as f:
                    f.write(file_content)

                file_size = file_path.stat().st_size
                log.info(f"[api/upload/file] saved: {file_path} ({file_size} bytes)")

                _send_json(200, {
                    "success": True,
                    "path": str(file_path),
                    "type": "application/octet-stream",
                    "size": f"{file_size} bytes"
                })
            except Exception as e:
                log.error(f"[api/upload/file] error: {e}", exc_info=True)
                _send_json(500, {"success": False, "error": str(e)})
            return

        # Handle other POST requests
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b"")

        try:
            data = json.loads(body.decode("utf-8"))
        except Exception as e:
            log.error(f"[http] parse error: {e}")
            return

        if self.path == "/test":
            msg = data.get("message", "")
            if msg:
                def _test():
                    result = agent(user_request=msg, conversation_history="", session_key="test")
                    log.info(f"[test] reply: {result.response[:200] if result.response else '(empty)'}")
                threading.Thread(target=_test, daemon=True).start()
            return

        if self.path == "/optimize":
            # Endpoint to trigger optimization
            def _optimize():
                from dspy_agent.utils import optimize_agent
                log.info("[optimize] Starting optimization...")
                # Would need training data - this is a placeholder
                log.info("[optimize] No training data provided, skipping")
            threading.Thread(target=_optimize, daemon=True).start()
            return

        threading.Thread(target=handle_callback, args=(data,), daemon=True).start()

    def log_message(self, format, *args):
        pass


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


# ============================================================
#  Main
# ============================================================

def main():
    scheduler.start()
    log.info(f"[dspy-agent] starting on port {PORT}")
    log.info(f"[dspy-agent] workspace={WORKSPACE}")
    log.info(f"[dspy-agent] owners={OWNER_IDS}")
    log.info(f"[dspy-agent] model={CONFIG['models']['default']}")
    log.info(f"[dspy-agent] files_dir={FILES_DIR}")

    server = ThreadedHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("[dspy-agent] shutting down")
        server.server_close()


if __name__ == "__main__":
    main()
