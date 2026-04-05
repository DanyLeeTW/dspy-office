"""
Messaging Platform API Wrapper

This module provides a simple interface for sending messages through
the messaging platform (WeChat Work/Enterprise WeChat).

For DSPy Agent, this provides the message sending capability.

Fallback Mode:
    When token/guid are placeholders (containing "YOUR_"), messages
    are printed to console instead of being sent to the API.
    This allows testing the agent without a real messaging platform.
"""

import json
import logging
import os
import time
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any

log = logging.getLogger("agent")

# Module state
_config = {}
_api_url = ""
_token = ""
_guid = ""
_fallback_mode = False  # When True, print to console instead of sending


def init(config: Dict[str, Any]) -> None:
    """
    Initialize messaging module with configuration.

    Args:
        config: Messaging configuration dict with token, guid, api_url
    """
    global _config, _api_url, _token, _guid, _fallback_mode

    _config = config
    _token = config.get("token", "")
    _guid = config.get("guid", "")
    _api_url = config.get("api_url", "http://api.messaging-platform.example.com/api/send")

    # Check if using placeholder credentials
    if "YOUR_" in _token or "YOUR_" in _guid or "example.com" in _api_url:
        _fallback_mode = True
        log.warning("[messaging] Placeholder credentials detected - using FALLBACK mode")
        log.warning("[messaging] Messages will be printed to console instead of being sent")

    log.info(f"[messaging] Initialized (guid={_guid[:8]}..., fallback={_fallback_mode})")


def is_fallback_mode() -> bool:
    """Check if messaging is in fallback mode (console output only)."""
    return _fallback_mode


def send_text(to_id: str, content: str) -> Dict[str, Any]:
    """
    Send a text message to a user.

    Args:
        to_id: Recipient user ID
        content: Message content

    Returns:
        API response dict
    """
    # Fallback mode: print to console
    if _fallback_mode:
        print(f"\n{'='*50}")
        print(f"[FALLBACK] Message to: {to_id}")
        print(f"{'='*50}")
        print(content)
        print(f"{'='*50}\n")
        log.info(f"[messaging] [FALLBACK] Would send to {to_id}: {content[:50]}...")
        return {"code": 0, "msg": "Fallback mode - printed to console"}

    if not _token or not _guid:
        log.warning("[messaging] Not configured, cannot send message")
        return {"code": -1, "msg": "Not configured"}

    body = json.dumps({
        "method": "/msg/sendText",
        "params": {"guid": _guid, "toId": str(to_id), "content": content},
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        _api_url,
        data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-API-TOKEN": _token,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("code") == 0:
                log.info(f"[messaging] Sent text to {to_id}")
            else:
                log.error(f"[messaging] Send failed: {result}")
            return result
    except Exception as e:
        log.error(f"[messaging] Send error: {e}")
        return {"code": -1, "msg": str(e)}


def send_image(to_id: str, image_path: str, caption: str = "") -> Dict[str, Any]:
    """
    Send an image to a user.

    Args:
        to_id: Recipient user ID
        image_path: Local file path or URL
        caption: Optional caption

    Returns:
        API response dict
    """
    # For now, just log and return success
    log.info(f"[messaging] Would send image to {to_id}: {image_path}")
    return {"code": 0, "msg": "Image send not implemented"}


def send_link(to_id: str, title: str, desc: str, url: str, icon_url: str = "") -> Dict[str, Any]:
    """
    Send a link card to a user.

    Args:
        to_id: Recipient user ID
        title: Link title
        desc: Link description
        url: Link URL
        icon_url: Optional icon URL

    Returns:
        API response dict
    """
    if not _token or not _guid:
        log.warning("[messaging] Not configured, cannot send link")
        return {"code": -1, "msg": "Not configured"}

    body = json.dumps({
        "method": "/msg/sendLink",
        "params": {
            "guid": _guid,
            "toId": str(to_id),
            "title": title,
            "desc": desc,
            "url": url,
            "iconUrl": icon_url,
        },
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        _api_url,
        data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-API-TOKEN": _token,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result
    except Exception as e:
        log.error(f"[messaging] Send link error: {e}")
        return {"code": -1, "msg": str(e)}


def upload_and_send(to_id: str, file_path: str, caption: str = "", workspace: str = ".") -> Dict[str, Any]:
    """
    Upload a file and send to user.

    Args:
        to_id: Recipient user ID
        file_path: Local file path or URL
        caption: Optional caption
        workspace: Workspace directory

    Returns:
        API response dict
    """
    # Check if URL
    if file_path.startswith("http://") or file_path.startswith("https://"):
        log.info(f"[messaging] Would download and send URL to {to_id}: {file_path}")
        return {"code": 0, "msg": "URL send not fully implemented"}

    # Local file
    if not os.path.exists(file_path):
        # Try workspace-relative path
        full_path = os.path.join(workspace, file_path)
        if not os.path.exists(full_path):
            log.error(f"[messaging] File not found: {file_path}")
            return {"code": -1, "msg": "File not found"}
        file_path = full_path

    log.info(f"[messaging] Would send file to {to_id}: {file_path}")
    return {"code": 0, "msg": "File send not fully implemented"}


def get_ext(filename: str) -> str:
    """Get file extension."""
    ext = os.path.splitext(filename)[1].lower()
    return ext if ext else ".bin"


def download_enterprise(file_id: str, aes_key: str, file_size: int, file_type: int = 5) -> Optional[str]:
    """
    Download file from enterprise platform.

    Args:
        file_id: File ID
        aes_key: AES key for decryption
        file_size: File size
        file_type: File type (1=image, 4=video, 5=file)

    Returns:
        Local file path or None
    """
    log.info(f"[messaging] Would download enterprise file: {file_id}")
    return None


def download_personal(aes_key: str, auth_key: str, url: str, file_size: int, file_type: int = 5) -> Optional[str]:
    """
    Download file from personal platform.

    Args:
        aes_key: AES key
        auth_key: Auth key
        url: File URL
        file_size: File size
        file_type: File type

    Returns:
        Local file path or None
    """
    log.info(f"[messaging] Would download personal file from {url}")
    return None
