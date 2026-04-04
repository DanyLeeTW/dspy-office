"""
DSPy Tools Module

This module provides a tool registry and DSPy-compatible tool wrappers.
Tools are regular Python functions that can be used by DSPy's ReAct agent.

Key differences from the original tools.py:
1. Tools are plain functions (no @tool decorator needed)
2. DSPy automatically infers tool schemas from function signatures
3. Tools can be used directly with dspy.ReAct

Migration from original tools.py:
    # Old (tools.py)
    @tool("exec", "Execute a shell command", {...}, ["command"])
    def tool_exec(args, ctx):
        return subprocess.run(args["command"], ...)

    # New (dspy_agent/tools.py)
    def exec(command: str, timeout: int = 60) -> str:
        '''Execute a shell command on the server.'''
        return subprocess.run(command, ...)
"""

import subprocess
import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error
import tempfile
import base64
import logging
import functools
from typing import Optional, List, Dict, Callable, Any

log = logging.getLogger("dspy_agent")


# ============================================================
#  Tool Registry (for backward compatibility and management)
# ============================================================

class ToolRegistry:
    """
    Registry for DSPy-compatible tools.

    Tools can be:
    1. Plain Python functions (DSPy infers schema)
    2. Functions with explicit schema via @tool decorator
    3. External MCP tools

    Usage:
        registry = ToolRegistry()

        # Register a plain function
        @registry.register
        def my_tool(query: str) -> str:
            '''Search for information.'''
            return f"Results for: {query}"

        # Get tools for DSPy ReAct
        tools = registry.get_tools()
        agent = dspy.ReAct("question -> answer", tools=tools)
    """

    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._schemas: Dict[str, Dict] = {}

    def register(self, func: Callable = None, *, name: str = None, schema: Dict = None):
        """
        Register a tool function.

        Can be used as decorator:
            @registry.register
            def my_tool(x: str) -> str:
                ...

        Or directly:
            registry.register(my_function, name="custom_name")
        """
        def decorator(f):
            tool_name = name or f.__name__
            self._tools[tool_name] = f
            if schema:
                self._schemas[tool_name] = schema
            return f

        if func is not None:
            return decorator(func)
        return decorator

    def get_tools(self) -> List[Callable]:
        """Get all registered tools for DSPy ReAct."""
        def _wrap(f):
            @functools.wraps(f)
            def wrapper(*args, **kwargs):
                # DSPy sometimes passes args as tool(kwargs={...}) — unpack it
                if kwargs.keys() == {'kwargs'} and isinstance(kwargs['kwargs'], dict):
                    kwargs = kwargs['kwargs']
                return f(*args, **kwargs)
            return wrapper
        return [_wrap(f) for f in self._tools.values()]

    def get_tool(self, name: str) -> Optional[Callable]:
        """Get a specific tool by name."""
        return self._tools.get(name)

    def get_schema(self, name: str) -> Optional[Dict]:
        """Get the JSON schema for a tool (if explicitly provided)."""
        return self._schemas.get(name)

    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def execute(self, name: str, **kwargs) -> str:
        """Execute a tool by name with given arguments."""
        tool = self._tools.get(name)
        if not tool:
            return f"[error] Tool '{name}' not found"
        try:
            result = tool(**kwargs)
            return str(result)
        except Exception as e:
            log.error(f"Tool '{name}' error: {e}", exc_info=True)
            return f"[error] {e}"


# Global registry instance
registry = ToolRegistry()


# ============================================================
#  Core Tools
# ============================================================

@registry.register
def exec(command: str, timeout: int = 60) -> str:
    """
    Execute a shell command on the server.

    Args:
        command: Shell command to execute
        timeout: Timeout in seconds (default 60, max 300)

    Returns:
        Command output (stdout and stderr combined)
    """
    timeout = min(timeout, 300)
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n[stderr] " + result.stderr) if output else result.stderr
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"[error] command timed out ({timeout}s)"


@registry.register
def message(content: str, owner_id: str = None) -> str:
    """
    Send a text message to the owner.

    Used for scheduled task notifications. Normal conversation replies don't need this tool.

    Args:
        content: Message content to send
        owner_id: Optional owner ID (uses default if not provided)

    Returns:
        Confirmation message
    """
    # Import messaging module at runtime to avoid circular imports
    import messaging

    # Message splitting for platform limits
    max_bytes = 1800
    if len(content.encode("utf-8")) <= max_bytes:
        chunks = [content]
    else:
        chunks = []
        current = ""
        for line in content.split("\n"):
            test = current + "\n" + line if current else line
            if len(test.encode("utf-8")) > max_bytes:
                if current:
                    chunks.append(current)
                current = line
            else:
                current = test
        if current:
            chunks.append(current)

    # Send via messaging platform
    if owner_id:
        for i, chunk in enumerate(chunks):
            messaging.send_text(owner_id, chunk)
            if i < len(chunks) - 1:
                time.sleep(0.5)
        return f"Sent to owner ({len(chunks)} messages)"
    return "No owner_id provided, message not sent"


# ============================================================
#  File Tools
# ============================================================

def _resolve_path(path: str, workspace: str = ".") -> str:
    """Resolve a path relative to workspace."""
    if os.path.isabs(path):
        return path
    return os.path.join(workspace, path)


@registry.register
def read_file(path: str, workspace: str = ".") -> str:
    """
    Read file content. Path relative to workspace directory.
    Supports text files and PDFs (extracts text from PDFs).

    Args:
        path: File path (relative to workspace or absolute)
        workspace: Workspace directory (default current directory)

    Returns:
        File content (truncated if > 10000 chars)
    """
    fpath = _resolve_path(path, workspace)
    try:
        # Check if PDF
        if fpath.lower().endswith('.pdf'):
            return _extract_pdf_text(fpath)

        # Regular text file
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        if len(content) > 10000:
            content = content[:10000] + f"\n... (truncated, total {len(content)} chars)"
        return content or "(empty file)"
    except FileNotFoundError:
        return f"[error] file not found: {fpath}"
    except Exception as e:
        return f"[error] {e}"


def _extract_pdf_text(fpath: str) -> str:
    """Extract text from PDF file using pdfplumber or pypdf."""
    try:
        # Try pdfplumber first (better text extraction)
        import pdfplumber
        text_parts = []
        with pdfplumber.open(fpath) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(f"--- Page {i+1} ---\n{page_text}")
        content = "\n\n".join(text_parts)
        if len(content) > 10000:
            content = content[:10000] + f"\n... (truncated, total {len(content)} chars)"
        return content or "(no text extracted from PDF)"
    except ImportError:
        pass

    # Fallback to pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(fpath)
        text_parts = []
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(f"--- Page {i+1} ---\n{page_text}")
        content = "\n\n".join(text_parts)
        if len(content) > 10000:
            content = content[:10000] + f"\n... (truncated, total {len(content)} chars)"
        return content or "(no text extracted from PDF)"
    except ImportError:
        return "[error] PDF support requires pdfplumber or pypdf. Install with: pip install pdfplumber"
    except Exception as e:
        return f"[error] Failed to extract PDF text: {e}"


@registry.register
def write_file(path: str, content: str, workspace: str = ".") -> str:
    """
    Write file (overwrite if exists). Path relative to workspace directory.

    Args:
        path: File path
        content: File content to write
        workspace: Workspace directory

    Returns:
        Confirmation with file size
    """
    fpath = _resolve_path(path, workspace)
    try:
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Written to {fpath} ({len(content)} chars)"
    except Exception as e:
        return f"[error] {e}"


@registry.register
def edit_file(path: str, old: str, new: str, workspace: str = ".") -> str:
    """
    Edit file: replace old text with new text.

    Args:
        path: File path
        old: Original text to replace
        new: Replacement text
        workspace: Workspace directory

    Returns:
        Confirmation message
    """
    fpath = _resolve_path(path, workspace)
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        if old not in content:
            return f"[error] old string not found in {fpath}"
        content = content.replace(old, new, 1)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Edited {fpath}"
    except FileNotFoundError:
        return f"[error] file not found: {fpath}"
    except Exception as e:
        return f"[error] {e}"


@registry.register
def list_files(file_type: str = "", limit: int = 20, workspace: str = ".") -> str:
    """
    List received and saved files.

    Args:
        file_type: Filter by type (image/video/file/voice/gif), empty for all
        limit: Number of results (default 20)
        workspace: Workspace directory

    Returns:
        List of files with metadata
    """
    index_path = os.path.join(workspace, "files", "index.json")
    if not os.path.exists(index_path):
        return "No files received yet."

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
    except Exception:
        return "File index read failed."

    if file_type:
        index = [e for e in index if e.get("type") == file_type]

    recent = index[-limit:]
    recent.reverse()

    if not recent:
        return f"No files of type '{file_type}' found." if file_type else "No files received yet."

    lines = [f"Total {len(index)} files" + (f" (type: {file_type})" if file_type else "") + f", showing {len(recent)} most recent:"]
    for e in recent:
        size_kb = e.get("size", 0) / 1024
        size_str = f"{size_kb/1024:.1f}MB" if size_kb > 1024 else f"{size_kb:.0f}KB"
        lines.append(f"  - [{e.get('type', '?')}] {e.get('filename', '?')} ({size_str}) {e.get('time', '?')}")
        lines.append(f"    Path: {e.get('path', '?')}")
    return "\n".join(lines)


@registry.register
def upload_file(url: str, filename: str = None, workspace: str = ".") -> str:
    """
    Download a file from URL and save to workspace/files/.

    Supports images, videos, PDFs, and other file types.
    Files are organized by month (YYYY-MM) and registered in the file index.

    Args:
        url: File URL to download (http/https)
        filename: Optional custom filename (auto-generated if not provided)
        workspace: Workspace directory

    Returns:
        Local file path and metadata
    """
    from datetime import datetime, timezone, timedelta

    if not url.startswith(("http://", "https://")):
        return f"[error] URL must start with http:// or https://"

    try:
        # Parse URL for filename
        parsed = urllib.parse.urlparse(url)
        url_filename = os.path.basename(urllib.parse.unquote(parsed.path))

        # Determine file extension
        ext = os.path.splitext(url_filename)[1]
        if not ext:
            # Try to get extension from content-type
            import urllib.request
            response = urllib.request.urlopen(url, timeout=30)
            content_type = response.headers.get("Content-Type", "")
            ext_map = {
                "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                "video/mp4": ".mp4", "video/webm": ".webm",
                "application/pdf": ".pdf",
                "application/zip": ".zip",
                "audio/mpeg": ".mp3", "audio/wav": ".wav"
            }
            ext = ext_map.get(content_type.split(";")[0], "")

        # Generate filename if not provided
        if not filename:
            filename = url_filename if url_filename else f"file_{int(time.time())}"
            if ext and not filename.endswith(ext):
                filename += ext

        # Create output directory (workspace/files/YYYY-MM/)
        cst = timezone(timedelta(hours=8))
        now = datetime.now(cst)
        out_dir = os.path.join(workspace, "files", now.strftime("%Y-%m"))
        os.makedirs(out_dir, exist_ok=True)

        # Generate unique filename if file exists
        base, ext_part = os.path.splitext(filename)
        counter = 1
        output_path = os.path.join(out_dir, filename)
        while os.path.exists(output_path):
            filename = f"{base}_{counter}{ext_part}"
            output_path = os.path.join(out_dir, filename)
            counter += 1

        # Download file
        log.info(f"[upload] downloading {url[:80]} -> {output_path}")
        urllib.request.urlretrieve(url, output_path)

        # Get file size
        file_size = os.path.getsize(output_path)

        # Determine file type
        ext_lower = ext.lower()
        if ext_lower in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
            file_type = "image"
        elif ext_lower in (".mp4", ".mov", ".avi", ".webm", ".mkv"):
            file_type = "video"
        elif ext_lower in (".mp3", ".wav", ".ogg", ".m4a"):
            file_type = "voice"
        else:
            file_type = "file"

        # Update file index
        index_path = os.path.join(workspace, "files", "index.json")
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            index = []

        entry = {
            "type": file_type,
            "filename": filename,
            "path": output_path,
            "size": file_size,
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "url": url
        }
        index.append(entry)

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

        size_str = f"{file_size/1024/1024:.1f}MB" if file_size > 1024*1024 else f"{file_size/1024:.0f}KB"
        log.info(f"[upload] saved: {output_path} ({size_str})")

        return f"File uploaded: {output_path}\nType: {file_type}, Size: {size_str}"

    except urllib.error.URLError as e:
        return f"[error] Download failed: {e}"
    except Exception as e:
        log.error(f"[upload] error: {e}", exc_info=True)
        return f"[error] {e}"


# ============================================================
#  Scheduler Tools
# ============================================================

@registry.register
def schedule(name: str, message: str, delay_seconds: int = None,
             cron_expr: str = None, once: bool = True) -> str:
    """
    Create a scheduled task.

    One-shot tasks use delay_seconds, recurring tasks use cron_expr.
    On trigger, the message is sent to LLM as a user message for processing.

    Args:
        name: Task name (unique identifier)
        message: Message sent to LLM on trigger
        delay_seconds: Delay in seconds (one-shot task)
        cron_expr: Cron expression (recurring task, e.g. '0 9 * * *')
        once: Execute only once (default true, for cron_expr)

    Returns:
        Confirmation message
    """
    import scheduler

    args = {
        "name": name,
        "message": message,
        "delay_seconds": delay_seconds,
        "cron_expr": cron_expr,
        "once": once
    }
    return scheduler.add(args)


@registry.register
def list_schedules() -> str:
    """
    List all scheduled tasks.

    Returns:
        List of scheduled tasks with status
    """
    import scheduler
    return scheduler.list_all()


@registry.register
def remove_schedule(name: str) -> str:
    """
    Delete a scheduled task.

    Args:
        name: Task name to delete

    Returns:
        Confirmation message
    """
    import scheduler
    return scheduler.remove(name)


# ============================================================
#  Media Tools
# ============================================================

@registry.register
def send_image(path: str, caption: str = "", owner_id: str = None,
               workspace: str = ".") -> str:
    """
    Send an image to the owner. Supports HTTP URL or local file path.

    Args:
        path: Image URL (http/https) or local file path
        caption: Optional text caption
        owner_id: Owner ID to send to
        workspace: Workspace directory for local files

    Returns:
        Confirmation message
    """
    import messaging
    if not owner_id:
        return "[error] No owner_id provided"
    result = messaging.upload_and_send(owner_id, path, caption, workspace)
    return "Image sent to owner" if result.get("code") == 0 else f"[error] Send failed: {result.get('msg', '?')}"


@registry.register
def send_file(path: str, caption: str = "", owner_id: str = None,
              workspace: str = ".") -> str:
    """
    Send a file to the owner (PDF, Excel, Word, ZIP, etc.).

    Args:
        path: File URL (http/https) or local file path
        caption: Optional text caption
        owner_id: Owner ID to send to
        workspace: Workspace directory

    Returns:
        Confirmation message
    """
    import messaging
    if not owner_id:
        return "[error] No owner_id provided"
    result = messaging.upload_and_send(owner_id, path, caption, workspace)
    return "File sent to owner" if result.get("code") == 0 else f"[error] Send failed: {result.get('msg', '?')}"


@registry.register
def send_video(path: str, caption: str = "", owner_id: str = None,
               workspace: str = ".") -> str:
    """
    Send a video to the owner. Supports HTTP URL or local MP4 file path.

    Args:
        path: Video URL (http/https) or local file path
        caption: Optional text caption
        owner_id: Owner ID to send to
        workspace: Workspace directory

    Returns:
        Confirmation message
    """
    import messaging
    if not owner_id:
        return "[error] No owner_id provided"
    result = messaging.upload_and_send(owner_id, path, caption, workspace)
    return "Video sent to owner" if result.get("code") == 0 else f"[error] Send failed: {result.get('msg', '?')}"


@registry.register
def send_link(title: str, desc: str, link_url: str, icon_url: str = "",
              owner_id: str = None) -> str:
    """
    Send a rich link card to the owner.

    Args:
        title: Card title
        desc: Card description
        link_url: Click-through URL
        icon_url: Card icon URL (optional)
        owner_id: Owner ID to send to

    Returns:
        Confirmation message
    """
    import messaging
    if not owner_id:
        return "[error] No owner_id provided"
    result = messaging.send_link(owner_id, title, desc, link_url, icon_url)
    return f"Link card sent: {title}" if result.get("code") == 0 else f"[error] Send failed: {result.get('msg', '?')}"


# ============================================================
#  Video Processing Tools
# ============================================================

def _ensure_local(path: str, label: str = "file") -> str:
    """If path is URL, download to /tmp/ and return local path."""
    if path.startswith("http://") or path.startswith("https://"):
        ext = os.path.splitext(urllib.parse.urlparse(path).path)[1] or ".mp4"
        local = f"/tmp/agent_{label}_{int(time.time())}{ext}"
        log.info(f"[video] downloading {path[:80]} -> {local}")
        urllib.request.urlretrieve(path, local)
        return local
    return path


def _video_output_path(workspace: str) -> str:
    """Generate output path under workspace/files/YYYY-MM/"""
    from datetime import datetime, timezone, timedelta
    cst = timezone(timedelta(hours=8))
    now = datetime.now(cst)
    out_dir = os.path.join(workspace, "files", now.strftime("%Y-%m"))
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"video_{now.strftime('%Y%m%d_%H%M%S')}.mp4")


@registry.register
def trim_video(input_path: str, start: str, end: str = None,
               send_to: str = None, workspace: str = ".") -> str:
    """
    Trim video: extract a time segment.

    Uses -c copy (no re-encoding), millisecond-fast even for large files.

    Args:
        input_path: Video file path (local or URL)
        start: Start time, format HH:MM:SS or seconds
        end: End time (optional, omit for until end)
        send_to: Send to whom after trimming (optional)
        workspace: Workspace directory

    Returns:
        Output file path and size
    """
    import messaging

    local_input = _ensure_local(input_path, "trim_in")
    output_path = _video_output_path(workspace)

    cmd = ["ffmpeg", "-y", "-ss", str(start)]
    if end:
        cmd += ["-to", str(end)]
    cmd += ["-i", local_input, "-c:v", "copy", "-c:a", "copy",
            "-avoid_negative_ts", "make_zero", output_path]

    log.info(f"[video] trim: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        return f"[error] ffmpeg trim failed: {result.stderr[-500:]}"

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    msg = f"Trim complete: {output_path} ({size_mb:.1f}MB)"

    if send_to:
        send_result = messaging.upload_and_send(send_to, output_path, "", workspace)
        if send_result.get("code") == 0:
            msg += ", sent"
        else:
            msg += f", send failed: {send_result.get('msg', '?')}"

    log.info(f"[video] {msg}")
    return msg


@registry.register
def add_bgm(video_path: str, audio_path: str, volume: float = 0.3,
            send_to: str = None, workspace: str = ".") -> str:
    """
    Add background music to video.

    Video stream not re-encoded (-c:v copy), only mixes audio tracks.

    Args:
        video_path: Video file path (local or URL)
        audio_path: Audio file path (mp3/wav/aac, local or URL)
        volume: BGM volume ratio (default 0.3 = 30%)
        send_to: Send to whom after processing (optional)
        workspace: Workspace directory

    Returns:
        Output file path and size
    """
    import messaging

    video = _ensure_local(video_path, "bgm_video")
    audio = _ensure_local(audio_path, "bgm_audio")
    output_path = _video_output_path(workspace)

    filter_complex = f"[1:a]volume={volume:.2f}[bgm];[0:a][bgm]amix=inputs=2:duration=first[a]"
    cmd = ["ffmpeg", "-y", "-i", video, "-i", audio,
           "-filter_complex", filter_complex,
           "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
           output_path]

    log.info(f"[video] add_bgm: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        return f"[error] ffmpeg BGM failed: {result.stderr[-500:]}"

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    msg = f"BGM added: {output_path} ({size_mb:.1f}MB)"

    if send_to:
        send_result = messaging.upload_and_send(send_to, output_path, "", workspace)
        if send_result.get("code") == 0:
            msg += ", sent"
        else:
            msg += f", send failed: {send_result.get('msg', '?')}"

    log.info(f"[video] {msg}")
    return msg


# ============================================================
#  Web Search Tool
# ============================================================

@registry.register
def web_search(query: str, source: str = "auto", count: int = 5) -> str:
    """
    Web search. Supports multiple search sources.

    Args:
        query: Search keywords
        source: Search source: auto/web/tavily/github/huggingface/all
        count: Number of results (default 5)

    Returns:
        Search results with summaries and links
    """
    # Import search functions from original tools module
    # This is a placeholder - full implementation would import from tools
    try:
        import tools as original_tools
        return original_tools.tool_web_search({
            "query": query,
            "source": source,
            "count": count
        }, {})
    except ImportError:
        # Fallback implementation
        return f"[web_search] Query: {query}, Source: {source}, Count: {count} (search module not available)"


# ============================================================
#  Memory Tools
# ============================================================

@registry.register
def search_memory(query: str, scope: str = "all", workspace: str = ".") -> str:
    """
    Search memory files. Uses keyword search in workspace/memory/ directory.

    Args:
        query: Search keywords (space-separated)
        scope: Search scope: all (default), long (MEMORY.md only), daily (daily logs only)
        workspace: Workspace directory

    Returns:
        Search results with file locations
    """
    memory_dir = os.path.join(workspace, "memory")
    if not os.path.isdir(memory_dir):
        return "Memory directory does not exist."

    grep_args = ["grep", "-r", "-i", "-n", "--include=*.md"]
    if scope == "long":
        target = os.path.join(memory_dir, "MEMORY.md")
        if not os.path.exists(target):
            return "MEMORY.md does not exist."
        grep_args = ["grep", "-i", "-n", "--", query, target]
    elif scope == "daily":
        grep_args.extend(["--include=2*.md", "--", query, memory_dir])
    else:
        grep_args.extend(["--", query, memory_dir])

    try:
        result = subprocess.run(grep_args, capture_output=True, text=True, timeout=10)
        output = result.stdout.strip()
        if not output:
            return f"No memories found containing '{query}'."

        lines = output.split("\n")
        if len(lines) > 30:
            return "\n".join(lines[:30]) + f"\n... {len(lines)} total matches, showing first 30"
        return f"{len(lines)} matches:\n" + "\n".join(lines)
    except Exception as e:
        return f"[error] Search failed: {e}"


@registry.register
def recall(query: str, session_key: str = None) -> str:
    """
    Semantic search in long-term memory.

    Use when the user asks about previous conversations or needs to recall historical information.
    More intelligent than search_memory (vector semantic matching vs keyword matching).

    Args:
        query: Search keywords or question
        session_key: Optional session key for context

    Returns:
        Relevant memories from vector search
    """
    try:
        import memory as mem_mod
        result = mem_mod.retrieve(query, session_key or "", top_k=10)
        return result or "No relevant memories found."
    except ImportError:
        return "[error] Memory module not available"


# ============================================================
#  Self-Check Tool
# ============================================================

@registry.register
def self_check(workspace: str = ".") -> str:
    """
    System self-check: collect today's conversation stats, system health,
    error logs, scheduled task status, etc.

    Used to generate daily self-check reports.

    Args:
        workspace: Workspace directory

    Returns:
        Diagnostic report
    """
    from datetime import datetime, timezone, timedelta

    cst = timezone(timedelta(hours=8))
    now = datetime.now(cst)
    today = now.strftime("%Y-%m-%d")
    report = []

    # 1. Today's active sessions
    sessions_dir = os.path.join(os.path.dirname(workspace), "sessions")
    active_sessions = 0
    total_user_msgs = 0
    total_assistant_msgs = 0
    total_tool_calls = 0

    if os.path.isdir(sessions_dir):
        for fname in os.listdir(sessions_dir):
            fpath = os.path.join(sessions_dir, fname)
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath), cst)
            if mtime.strftime("%Y-%m-%d") == today:
                active_sessions += 1
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        msgs = json.load(f)
                    for m in msgs:
                        if m.get("role") == "user":
                            total_user_msgs += 1
                        elif m.get("role") == "assistant":
                            total_assistant_msgs += 1
                            if m.get("tool_calls"):
                                total_tool_calls += len(m["tool_calls"])
                except Exception:
                    pass

    report.append(f"== Today's Conversations ({today}) ==")
    report.append(f"Active sessions: {active_sessions}")
    report.append(f"User messages: {total_user_msgs}, Assistant replies: {total_assistant_msgs}, Tool calls: {total_tool_calls}")

    # 2. Today's error logs
    try:
        err_cmd = 'journalctl -u agent --since today --no-pager | grep -ci "error"'
        err_result = subprocess.run(["bash", "-c", err_cmd], capture_output=True, text=True, timeout=10)
        err_count = err_result.stdout.strip() or "0"
        report.append("\n== Error Logs ==")
        report.append(f"Today's errors: {err_count}")
        if int(err_count) > 0:
            last_cmd = 'journalctl -u agent --since today --no-pager | grep -i "error" | tail -5'
            last_errs = subprocess.run(["bash", "-c", last_cmd], capture_output=True, text=True, timeout=10).stdout.strip()
            if last_errs:
                report.append("Last 5:\n" + last_errs)
    except Exception as e:
        report.append(f"\n== Error Logs ==\nRead failed: {e}")

    # 3. Service uptime
    try:
        uptime_result = subprocess.run(
            ["systemctl", "show", "agent", "--property=ActiveEnterTimestamp", "--value"],
            capture_output=True, text=True, timeout=5
        )
        report.append("\n== System Status ==")
        report.append(f"Service start time: {uptime_result.stdout.strip()}")
    except Exception:
        pass

    # 4. Memory and disk
    try:
        mem = subprocess.run(["bash", "-c", "free -h | grep Mem"], capture_output=True, text=True, timeout=5).stdout.strip()
        disk = subprocess.run(["bash", "-c", "df -h /data | tail -1"], capture_output=True, text=True, timeout=5).stdout.strip()
        report.append(f"Memory: {mem}")
        report.append(f"Disk: {disk}")
    except Exception:
        pass

    # 5. Scheduled task status
    try:
        jobs_file = os.path.join(os.path.dirname(workspace), "jobs.json")
        with open(jobs_file, "r", encoding="utf-8") as f:
            jobs = json.load(f)
        report.append(f"\n== Scheduled Tasks ({len(jobs)}) ==")
        for j in jobs:
            cron = j.get("cron_expr", "")
            last = j.get("last_run")
            last_str = datetime.fromtimestamp(last, cst).strftime("%H:%M") if last else "never"
            report.append(f"  - {j['name']} ({cron}) last: {last_str}")
    except Exception as e:
        report.append(f"\n== Scheduled Tasks ==\nRead failed: {e}")

    return "\n".join(report)


# ============================================================
#  Diagnostics Tool
# ============================================================

@registry.register
def diagnose(target: str = "all", workspace: str = ".") -> str:
    """
    Diagnose system problems.

    Check session file health, MCP server connection status, recent error log details.
    Call this first when encountering 400 errors, MCP tool unavailability, or any anomaly.

    Args:
        target: Diagnosis target: 'session', 'mcp', 'errors', 'all'
        workspace: Workspace directory

    Returns:
        Diagnostic report
    """
    report = []

    if target in ("session", "all"):
        report.append("== Session File Health Check ==")
        sessions_dir = os.path.join(os.path.dirname(workspace), "sessions")
        if os.path.isdir(sessions_dir):
            for fname in sorted(os.listdir(sessions_dir)):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(sessions_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        msgs = json.load(f)
                    issues = []
                    if msgs and msgs[0].get("role") == "tool":
                        issues.append("Starts with orphan tool message (causes LLM 400)")
                    if msgs and msgs[0].get("role") == "assistant" and msgs[0].get("tool_calls"):
                        issues.append("Starts with assistant+tool_calls (missing tool results)")
                    status = "ISSUES" if issues else "OK"
                    report.append(f"  {fname}: {len(msgs)} msgs, {status}")
                    for issue in issues:
                        report.append(f"    WARNING: {issue}")
                except Exception as e:
                    report.append(f"  {fname}: read failed ({e})")
        else:
            report.append("  sessions directory does not exist")

    if target in ("errors", "all"):
        report.append("\n== Recent Error Details ==")
        try:
            cmd = 'journalctl -u agent --no-pager -n 500 --since "1 hour ago" | grep -B 1 -A 2 "ERROR\\|400\\|Bad Request" | tail -30'
            result = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=10)
            errors = result.stdout.strip()
            if errors:
                report.append(errors)
            else:
                report.append("  No errors in last hour")
        except Exception as e:
            report.append(f"  Read failed: {e}")

    return "\n".join(report)


# ============================================================
#  Tool Creation (Self-Evolution)
# ============================================================

@registry.register
def create_tool(name: str, code: str, workspace: str = ".") -> str:
    """
    Create a new custom tool plugin.

    Code is saved to plugins/ directory and hot-loaded immediately.
    Use standard Python function syntax. The function will be registered automatically.

    Args:
        name: Tool name (used as filename, e.g. 'weather' creates plugins/weather.py)
        code: Complete Python function code
        workspace: Workspace directory

    Returns:
        Confirmation message
    """
    # Validate tool name
    if not name.replace("_", "").isalnum():
        return "[error] Tool name can only contain letters, digits, and underscores"

    plugins_dir = os.path.join(workspace, "plugins")
    plugin_path = os.path.join(plugins_dir, f"{name}.py")

    # Check if it's overwriting a built-in tool
    if name in registry._tools and not os.path.exists(plugin_path):
        return f"[error] Cannot overwrite built-in tool '{name}'"

    # Try loading first to validate code
    try:
        exec(compile(code, f"{name}.py", "exec"), {"__builtins__": __builtins__})
    except Exception as e:
        return f"[error] Code execution failed: {e}"

    # Validation passed, persist to disk
    os.makedirs(plugins_dir, exist_ok=True)
    with open(plugin_path, "w", encoding="utf-8") as f:
        f.write(code)

    log.info(f"[plugins] created: {name}.py")
    return f"Created custom tool '{name}', saved at plugins/{name}.py"


@registry.register
def list_custom_tools(workspace: str = ".") -> str:
    """
    List all custom tool plugins (in plugins/ directory).

    Args:
        workspace: Workspace directory

    Returns:
        List of custom tools with status
    """
    plugins_dir = os.path.join(workspace, "plugins")
    if not os.path.isdir(plugins_dir):
        return "No custom tools yet. plugins/ directory does not exist."

    plugins = [f for f in sorted(os.listdir(plugins_dir)) if f.endswith(".py")]
    if not plugins:
        return "No custom tools yet."

    lines = [f"Custom tools ({len(plugins)}):"]
    for fname in plugins:
        tool_name = fname[:-3]
        fpath = os.path.join(plugins_dir, fname)
        size = os.path.getsize(fpath)
        status = "loaded" if tool_name in registry._tools else "not loaded"
        lines.append(f"  - {tool_name} ({status}, {size} bytes)")

    return "\n".join(lines)


@registry.register
def remove_tool(name: str, workspace: str = ".") -> str:
    """
    Delete a custom tool plugin. Can only delete plugins/ tools, not built-in tools.

    Args:
        name: Tool name to delete
        workspace: Workspace directory

    Returns:
        Confirmation message
    """
    plugins_dir = os.path.join(workspace, "plugins")
    plugin_path = os.path.join(plugins_dir, f"{name}.py")

    if not os.path.exists(plugin_path):
        return f"[error] Custom tool '{name}' does not exist (can only delete plugins/ tools)"

    os.remove(plugin_path)
    if name in registry._tools:
        del registry._tools[name]

    log.info(f"[plugins] removed: {name}")
    return f"Deleted custom tool '{name}'"


# ============================================================
#  NotebookLM Tools
# ============================================================

def _ensure_mcp_initialized():
    """Ensure MCP client is initialized for NotebookLM tools."""
    try:
        import mcp_client
        if not hasattr(mcp_client, '_servers') or not mcp_client._servers:
            import json
            config_path = os.environ.get("AGENT_CONFIG", "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    cfg = json.load(f)
                mcp_client.init(cfg)
    except Exception as e:
        log.warning(f"[nlm] MCP init failed: {e}")


@registry.register
def nlm_create_notebook(title: str = "") -> str:
    """
    Create a new NotebookLM notebook.

    Args:
        title: Optional title for the notebook

    Returns:
        Notebook ID and creation status
    """
    try:
        _ensure_mcp_initialized()
        import mcp_client
        result = mcp_client.execute("notebooklm__notebook_create", {"title": title})
        return result
    except Exception as e:
        return f"[error] {e}"


@registry.register
def nlm_list_notebooks(max_results: int = 100) -> str:
    """
    List all NotebookLM notebooks.

    Args:
        max_results: Maximum number of notebooks to return (default 100)

    Returns:
        List of notebooks with IDs and titles
    """
    try:
        _ensure_mcp_initialized()
        import mcp_client
        result = mcp_client.execute("notebooklm__notebook_list", {"max_results": max_results})
        return result
    except Exception as e:
        return f"[error] {e}"


@registry.register
def nlm_add_source(notebook_id: str, source_type: str, url: str = None,
                   text: str = None, file_path: str = None, title: str = None) -> str:
    """
    Add a source to a NotebookLM notebook.

    Supports: url, text, drive, file

    Args:
        notebook_id: Notebook UUID
        source_type: Type of source (url/text/drive/file)
        url: URL for web pages or YouTube (source_type=url)
        text: Text content (source_type=text)
        file_path: Local file path for PDF/text/audio (source_type=file)
        title: Display title (for text sources)

    Returns:
        Source addition status
    """
    try:
        _ensure_mcp_initialized()
        import mcp_client
        args = {"notebook_id": notebook_id, "source_type": source_type}
        if url:
            args["url"] = url
        if text:
            args["text"] = text
        if file_path:
            args["file_path"] = file_path
        if title:
            args["title"] = title
        result = mcp_client.execute("notebooklm__source_add", args)
        return result
    except Exception as e:
        return f"[error] {e}"


@registry.register
def nlm_query(notebook_id: str, query: str, source_ids: List[str] = None) -> str:
    """
    Ask AI about sources in a NotebookLM notebook.

    Args:
        notebook_id: Notebook UUID
        query: Question to ask
        source_ids: Optional list of source IDs to query (default: all)

    Returns:
        AI response with citations
    """
    try:
        _ensure_mcp_initialized()
        import mcp_client
        args = {"notebook_id": notebook_id, "query": query}
        if source_ids:
            args["source_ids"] = source_ids
        result = mcp_client.execute("notebooklm__notebook_query", args)
        return result
    except Exception as e:
        return f"[error] {e}"


@registry.register
def nlm_create_audio(notebook_id: str, audio_format: str = "deep_dive",
                     audio_length: str = "default") -> str:
    """
    Create an Audio Overview (podcast) from notebook sources.

    Args:
        notebook_id: Notebook UUID
        audio_format: Format type (deep_dive/brief/critique/debate)
        audio_length: Length (short/default/long)

    Returns:
        Audio generation status and URL when complete
    """
    try:
        _ensure_mcp_initialized()
        import mcp_client
        args = {
            "notebook_id": notebook_id,
            "artifact_type": "audio",
            "audio_format": audio_format,
            "audio_length": audio_length,
            "confirm": True
        }
        result = mcp_client.execute("notebooklm__studio_create", args)
        return result
    except Exception as e:
        return f"[error] {e}"


@registry.register
def nlm_create_mindmap(notebook_id: str, title: str = "Mind Map") -> str:
    """
    Create a mind map from notebook sources.

    Args:
        notebook_id: Notebook UUID
        title: Title for the mind map

    Returns:
        Mind map generation status
    """
    try:
        _ensure_mcp_initialized()
        import mcp_client
        args = {
            "notebook_id": notebook_id,
            "artifact_type": "mind_map",
            "title": title,
            "confirm": True
        }
        result = mcp_client.execute("notebooklm__studio_create", args)
        return result
    except Exception as e:
        return f"[error] {e}"


@registry.register
def nlm_create_quiz(notebook_id: str, question_count: int = 5,
                    difficulty: str = "medium") -> str:
    """
    Create a quiz from notebook sources.

    Args:
        notebook_id: Notebook UUID
        question_count: Number of questions (default 5)
        difficulty: Difficulty level (easy/medium/hard)

    Returns:
        Quiz generation status
    """
    try:
        _ensure_mcp_initialized()
        import mcp_client
        args = {
            "notebook_id": notebook_id,
            "artifact_type": "quiz",
            "question_count": question_count,
            "difficulty": difficulty,
            "confirm": True
        }
        result = mcp_client.execute("notebooklm__studio_create", args)
        return result
    except Exception as e:
        return f"[error] {e}"


@registry.register
def nlm_research(query: str, mode: str = "fast", source: str = "web",
                 notebook_id: str = None, title: str = None) -> str:
    """
    Deep research: search web or Google Drive to find new sources.

    Args:
        query: What to search for
        mode: Research mode (fast ~30s ~10 sources, or deep ~5min ~40 sources)
        source: Where to search (web or drive)
        notebook_id: Existing notebook ID (creates new if not provided)
        title: Title for new notebook

    Returns:
        Research task status
    """
    try:
        _ensure_mcp_initialized()
        import mcp_client
        args = {
            "query": query,
            "mode": mode,
            "source": source
        }
        if notebook_id:
            args["notebook_id"] = notebook_id
        if title:
            args["title"] = title
        result = mcp_client.execute("notebooklm__research_start", args)
        return result
    except Exception as e:
        return f"[error] {e}"


@registry.register
def nlm_download_audio(notebook_id: str, output_path: str) -> str:
    """
    Download Audio Overview from notebook.

    Args:
        notebook_id: Notebook UUID
        output_path: Path to save the audio file (e.g., /path/to/podcast.mp3)

    Returns:
        Download status and file path
    """
    try:
        _ensure_mcp_initialized()
        import mcp_client
        args = {
            "notebook_id": notebook_id,
            "artifact_type": "audio",
            "output_path": output_path
        }
        result = mcp_client.execute("notebooklm__download_artifact", args)
        return result
    except Exception as e:
        return f"[error] {e}"


# ============================================================
#  Export for DSPy ReAct
# ============================================================

def get_all_tools() -> List[Callable]:
    """
    Get all registered tools for DSPy ReAct agent.

    Usage:
        tools = get_all_tools()
        agent = dspy.ReAct("question -> answer", tools=tools)
    """
    return registry.get_tools()


