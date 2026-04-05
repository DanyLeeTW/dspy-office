"""
SSEEmitter - Server-Sent Events Streaming

Provides utilities for emitting SSE events in HTTP responses.
SSE enables real-time streaming of agent thoughts, tool calls, and responses.

Usage:
    # In HTTP handler
    emitter = SSEEmitter(wfile)

    # Send headers
    emitter.start()

    # Send events
    emitter.emit("thinking", {"content": "Processing..."})
    emitter.emit("tool_start", {"tool": "read_file", "args": {...}})
    emitter.emit("tool_end", {"tool": "read_file", "result": "..."})
    emitter.emit("response", {"content": "Final answer"})
    emitter.emit("done", {})
"""

import json
import logging
from typing import Any, Dict, BinaryIO

log = logging.getLogger("dspy_agent")


class SSEEmitter:
    """
    Server-Sent Events emitter for HTTP streaming.

    Wraps a writable file-like object (wfile) and provides
    methods for sending SSE-formatted events.

    SSE Format:
        event: <event_type>
        data: <json_data>

        (blank line terminates event)
    """

    def __init__(self, wfile: BinaryIO):
        """
        Initialize SSE emitter.

        Args:
            wfile: Writable binary file-like object from HTTP response
        """
        self.wfile = wfile
        self._started = False

    def start(self) -> None:
        """Send SSE headers to start streaming."""
        self.wfile.write(b"HTTP/1.1 200 OK\r\n")
        self.wfile.write(b"Content-Type: text/event-stream\r\n")
        self.wfile.write(b"Cache-Control: no-cache\r\n")
        self.wfile.write(b"Connection: keep-alive\r\n")
        self.wfile.write(b"Access-Control-Allow-Origin: *\r\n")
        self.wfile.write(b"\r\n")
        self.wfile.flush()
        self._started = True
        log.debug("[sse] stream started")

    def emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Send an SSE event.

        Args:
            event_type: Event name (e.g., "thinking", "tool_start", "response")
            data: Event payload (will be JSON-encoded)
        """
        event = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        self.wfile.write(event.encode("utf-8"))
        self.wfile.flush()

    def thinking(self, content: str = "Processing request...") -> None:
        """Send a thinking/processing event."""
        self.emit("thinking", {"content": content})

    def tool_start(self, tool: str, args: Dict[str, Any]) -> None:
        """Send a tool execution start event."""
        self.emit("tool_start", {"tool": tool, "args": args})

    def tool_end(self, tool: str, result: str) -> None:
        """Send a tool execution end event."""
        # Truncate long results
        if len(result) > 500:
            result = result[:500] + "..."
        self.emit("tool_end", {"tool": tool, "result": result})

    def response(self, content: str, memory_context: str = "") -> None:
        """Send the final response event."""
        self.emit("response", {
            "content": content,
            "memory_context": memory_context,
        })

    def error(self, message: str) -> None:
        """Send an error event."""
        self.emit("error", {"message": message})
        log.warning(f"[sse] error event: {message}")

    def done(self) -> None:
        """Send the done event to signal stream end."""
        self.emit("done", {})

    def send_json(self, status: int, payload: Dict[str, Any]) -> None:
        """
        Send a regular JSON response (non-streaming).

        Args:
            status: HTTP status code
            payload: Response data
        """
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.wfile.write(f"HTTP/1.1 {status} OK\r\n".encode())
        self.wfile.write(b"Content-Type: application/json; charset=utf-8\r\n")
        self.wfile.write(f"Content-Length: {len(encoded)}\r\n".encode())
        self.wfile.write(b"Access-Control-Allow-Origin: *\r\n")
        self.wfile.write(b"\r\n")
        self.wfile.write(encoded)
        self.wfile.flush()
