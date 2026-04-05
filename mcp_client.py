"""
MCP Client - Connect to external MCP Servers, register their tools into the agent

Self-implemented JSON-RPC (no MCP SDK), zero new dependencies.
MCP protocol only needs 3 methods: initialize, tools/list, tools/call.

Transport Support:
  - stdio: subprocess with stdin/stdout (serialized, one request at a time)
  - http: HTTP POST to MCP endpoint (concurrent requests supported)
  - sse: Server-Sent Events (concurrent requests supported)

Usage (called by tools.py):
  mcp_client.init(config)           # Connect all config["mcp_servers"]
  mcp_client.get_all_tool_defs()    # Return OpenAI function calling format
  mcp_client.execute(name, args)    # Call (name = servername__toolname)
  mcp_client.shutdown()             # Close all server processes
"""

import json
import logging
import os
import select
import subprocess
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger("agent")

# ============================================================
#  MCPServer - Single MCP Server Connection
# ============================================================

class MCPServer:
    """Manage lifecycle and JSON-RPC communication for one MCP server.

    Transport modes:
    - stdio: subprocess with stdin/stdout (serialized via lock)
    - http: HTTP POST to MCP endpoint (concurrent, session-based)
    - sse: Server-Sent Events (concurrent, session-based)

    For concurrent tool execution, use http or sse transport.
    notebooklm-mcp supports: --transport http|sse
    """

    def __init__(self, name, config):
        self.name = name
        self.config = config
        self.transport = config.get("transport", "stdio")
        self._proc = None
        self._lock = threading.Lock()  # Protect stdio read/write (not used for http/sse)
        self._req_id = 0
        self._req_id_lock = threading.Lock()  # Thread-safe request ID generation
        self._session_id = None  # HTTP transport session
        self._tools = []  # MCP raw tool definitions

    # ------ Lifecycle ------

    def start(self):
        """Start server process (stdio) or verify connectivity (HTTP), then handshake"""
        if self.transport == "stdio":
            self._start_stdio()
        # HTTP doesn't need to start a process
        self._initialize()
        self._discover_tools()
        log.info("[mcp] %s: connected, %d tools" % (self.name, len(self._tools)))

    def shutdown(self):
        """Shut down server process"""
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.close()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
            log.info("[mcp] %s: shut down" % self.name)

    def _start_stdio(self):
        """Start subprocess, communicate via stdin/stdout"""
        cmd = self.config.get("command", "")
        args = self.config.get("args", [])
        env = {**os.environ, **self.config.get("env", {})}

        # Capture stderr in debug mode for diagnostics
        stderr_mode = subprocess.PIPE if os.environ.get("MCP_DEBUG") else subprocess.DEVNULL

        self._proc = subprocess.Popen(
            [cmd] + args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_mode,
            env=env,
        )

        # Start stderr reader thread in debug mode
        if os.environ.get("MCP_DEBUG") and self._proc.stderr:
            def _stderr_reader():
                try:
                    for line in self._proc.stderr:
                        log.debug("[mcp] %s stderr: %s" % (self.name, line.decode().strip()))
                except Exception:
                    pass
            threading.Thread(target=_stderr_reader, daemon=True, name=f"mcp-stderr-{self.name}").start()

    def _reconnect(self):
        """Reconnect once after crash"""
        log.warning("[mcp] %s: reconnecting..." % self.name)
        try:
            self.shutdown()
        except Exception:
            pass
        try:
            if self.transport == "stdio":
                self._start_stdio()
            self._initialize()
            self._discover_tools()
            log.info("[mcp] %s: reconnected, %d tools" % (self.name, len(self._tools)))
            return True
        except Exception as e:
            log.error("[mcp] %s: reconnect failed: %s" % (self.name, e))
            return False

    # ------ JSON-RPC ------

    def _next_id(self):
        """Thread-safe request ID generation"""
        with self._req_id_lock:
            self._req_id += 1
            return self._req_id

    def _request(self, method, params=None, capture_session=False):
        """Send JSON-RPC request, return result"""
        msg = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params is not None:
            msg["params"] = params

        if self.transport == "stdio":
            return self._stdio_request(msg)
        else:
            return self._http_request(msg, capture_session=capture_session)

    def _stdio_request(self, msg):
        """stdio transport: write JSON+newline to stdin, read response from stdout.

        Uses select() instead of a thread-per-request to avoid OS thread spawn overhead.
        Matches response by request ID so MCP notifications are skipped, not mistaken
        for the real reply.
        """
        with self._lock:
            if not self._proc or self._proc.poll() is not None:
                raise ConnectionError("MCP server %s process not running" % self.name)

            self._proc.stdin.write((json.dumps(msg) + "\n").encode())
            self._proc.stdin.flush()

            expected_id = msg.get("id")
            deadline = time.monotonic() + 30

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("MCP server %s: request timed out (30s)" % self.name)

                ready, _, _ = select.select([self._proc.stdout], [], [], remaining)
                if not ready:
                    raise TimeoutError("MCP server %s: request timed out (30s)" % self.name)

                raw = self._proc.stdout.readline()
                if not raw:
                    raise ConnectionError("MCP server %s: stdout EOF" % self.name)
                raw = raw.strip()
                if not raw:
                    continue

                try:
                    resp = json.loads(raw)
                except json.JSONDecodeError:
                    continue  # skip non-JSON lines (startup banners, npm warnings)

                # Skip notifications — they have no "id" field
                if resp.get("id") != expected_id:
                    continue

                if "error" in resp:
                    err = resp["error"]
                    raise RuntimeError("MCP server %s: %s (code=%s)" % (
                        self.name, err.get("message", ""), err.get("code", "?")))
                return resp.get("result")

    def _http_request(self, msg, capture_session=False):
        """HTTP transport: POST JSON-RPC to server URL

        MCP HTTP transport requires:
        - Content-Type: application/json
        - Accept: application/json, text/event-stream
        - mcp-session-id header (after initialization)

        Response is SSE format: "event: message\ndata: {...}\n\n"
        """
        url = self.config.get("url", "")
        body = json.dumps(msg).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        # Include session ID if we have one
        if self._session_id:
            headers["mcp-session-id"] = self._session_id

        req = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                # Capture session ID from response headers
                if capture_session:
                    session_id = r.headers.get("mcp-session-id")
                    if session_id:
                        self._session_id = session_id
                        log.info("[mcp] %s: session %s" % (self.name, session_id))
                raw = r.read().decode("utf-8")
        except Exception as e:
            raise ConnectionError("MCP server %s HTTP error: %s" % (self.name, e))

        # Parse SSE format: "event: message\ndata: {...}\n\n"
        # Find the data line and extract JSON
        resp = None
        for line in raw.split("\n"):
            if line.startswith("data: "):
                try:
                    resp = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                break

        if resp is None:
            raise ConnectionError("MCP server %s: invalid SSE response" % self.name)

        if "error" in resp:
            err = resp["error"]
            raise RuntimeError("MCP server %s: %s (code=%s)" % (
                self.name, err.get("message", ""), err.get("code", "?")))
        return resp.get("result")

    # ------ MCP Protocol Methods ------

    def _initialize(self):
        """MCP handshake"""
        # Initialize and capture session ID for HTTP transport
        self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "724-office", "version": "1.0"},
        }, capture_session=True)
        # Send initialized notification (no id = notification)
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        if self.transport == "stdio" and self._proc:
            with self._lock:
                self._proc.stdin.write((json.dumps(notif) + "\n").encode())
                self._proc.stdin.flush()

    def _discover_tools(self):
        """Get tool list from server"""
        result = self._request("tools/list")
        self._tools = result.get("tools", []) if result else []

    def call_tool(self, tool_name, arguments):
        """Call a tool on the server"""
        try:
            result = self._request("tools/call", {
                "name": tool_name,
                "arguments": arguments or {},
            })
        except (ConnectionError, TimeoutError) as e:
            log.warning("[mcp] %s: call failed (%s), trying reconnect" % (
                self.name, e))
            if self.transport == "stdio" and self._reconnect():
                result = self._request("tools/call", {
                    "name": tool_name,
                    "arguments": arguments or {},
                })
            else:
                raise

        # MCP returns content array, concatenate into text
        if not result:
            return ""
        content = result.get("content", [])
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return "\n".join(parts) if parts else json.dumps(result, ensure_ascii=False)

    def get_tool_defs(self):
        """Convert MCP tool definitions to OpenAI function calling format

        Namespace: servername__toolname (double underscore)
        MCP inputSchema -> OpenAI function.parameters (same structure, reuse directly)
        """
        defs = []
        for t in self._tools:
            mcp_name = t.get("name", "")
            namespaced = "%s__%s" % (self.name, mcp_name)
            schema = t.get("inputSchema", {"type": "object", "properties": {}})
            defs.append({
                "type": "function",
                "function": {
                    "name": namespaced,
                    "description": t.get("description", "MCP tool: %s" % mcp_name),
                    "parameters": schema,
                },
            })
        return defs


# ============================================================
#  Module-Level API
# ============================================================

_servers = {}  # name -> MCPServer


def init(config):
    """Connect all configured MCP servers"""
    mcp_config = config.get("mcp_servers", {})
    if not mcp_config:
        return

    for name, srv_config in mcp_config.items():
        try:
            server = MCPServer(name, srv_config)
            server.start()
            _servers[name] = server
        except Exception as e:
            # Single server failure doesn't affect other servers or built-in tools
            log.error("[mcp] %s: failed to start: %s" % (name, e))


def get_all_tool_defs():
    """Return all MCP server tool definitions (OpenAI format)"""
    defs = []
    for server in _servers.values():
        defs.extend(server.get_tool_defs())
    return defs


def execute(name, args):
    """Call MCP tool (name format: servername__toolname)"""
    parts = name.split("__", 1)
    if len(parts) != 2:
        return "[error] invalid MCP tool name: %s" % name
    server_name, tool_name = parts
    server = _servers.get(server_name)
    if not server:
        return "[error] MCP server not found: %s" % server_name
    try:
        return server.call_tool(tool_name, args)
    except Exception as e:
        log.error("[mcp] %s call error: %s" % (name, e))
        return "[error] MCP tool %s failed: %s" % (name, e)


def reload(config):
    """Hot-reload: close old connections, reconnect all MCP servers with new config
    Returns (added, removed, total) for logging
    """
    old_names = set(_servers.keys())
    shutdown()
    init(config)
    new_names = set(_servers.keys())
    added = new_names - old_names
    removed = old_names - new_names
    return added, removed, len(_servers)


def shutdown():
    """Shut down all MCP servers"""
    for name, server in _servers.items():
        try:
            server.shutdown()
        except Exception as e:
            log.error("[mcp] %s shutdown error: %s" % (name, e))
    _servers.clear()
    log.info("[mcp] all servers shut down")
