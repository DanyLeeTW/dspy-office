"""
DebounceBuffer - Message Debouncing for IM Platforms

Buffers incoming messages and flushes after a delay, merging multiple
rapid messages into a single request. This is useful for IM platforms
where users may send multiple short messages in quick succession.

Usage:
    buffer = DebounceBuffer(delay_seconds=1.0, flush_callback=handle_flush)

    # Buffer a message
    buffer.add(sender_id="user123", text="Hello")

    # After 1 second of no new messages, flush_callback is called
    # with merged text and collected images
"""

import threading
import logging
from typing import Callable, Dict, List, Any, Optional

log = logging.getLogger("dspy_agent")


class DebounceBuffer:
    """
    Thread-safe message debouncing buffer.

    Buffers messages per sender and flushes after a configurable delay,
    merging all buffered messages into a single callback invocation.

    Attributes:
        delay_seconds: Time to wait before flushing (default from config)
        flush_callback: Function called with (sender_id, merged_text, images)
        prefetch_callback: Optional function to prefetch embeddings
    """

    def __init__(
        self,
        delay_seconds: float = 3.0,
        flush_callback: Optional[Callable[[str, str, List], None]] = None,
        prefetch_callback: Optional[Callable[[str], None]] = None,
    ):
        self.delay_seconds = delay_seconds
        self.flush_callback = flush_callback
        self.prefetch_callback = prefetch_callback

        # Per-sender buffers
        self._buffers: Dict[str, List[Dict[str, Any]]] = {}
        self._timers: Dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def add(
        self,
        sender_id: str,
        text: str,
        images: Optional[List] = None,
    ) -> int:
        """
        Add a message to the buffer for the given sender.

        Args:
            sender_id: Unique identifier for the sender
            text: Message text content
            images: Optional list of images

        Returns:
            Number of buffered messages for this sender (after adding)
        """
        # Prefetch embedding for the text (non-blocking)
        if self.prefetch_callback and text:
            try:
                self.prefetch_callback(text)
            except Exception as e:
                log.warning(f"[debounce] prefetch error: {e}")

        with self._lock:
            # Add fragment to buffer
            fragment = {"text": text, "images": images or []}
            self._buffers.setdefault(sender_id, []).append(fragment)

            # Cancel existing timer
            old_timer = self._timers.get(sender_id)
            if old_timer:
                old_timer.cancel()

            # Schedule flush
            timer = threading.Timer(
                self.delay_seconds,
                self._flush,
                args=[sender_id],
            )
            timer.daemon = True
            timer.start()
            self._timers[sender_id] = timer

            count = len(self._buffers[sender_id])
            log.info(f"[debounce] {sender_id}: buffered #{count}")
            return count

    def _flush(self, sender_id: str) -> None:
        """Internal flush handler called by timer."""
        with self._lock:
            fragments = self._buffers.pop(sender_id, [])
            self._timers.pop(sender_id, None)

        if not fragments:
            return

        # Merge fragments
        texts = []
        images = []
        for frag in fragments:
            if frag.get("text"):
                texts.append(frag["text"])
            images.extend(frag.get("images", []))

        merged_text = "\n".join(texts)
        if len(fragments) > 1:
            log.info(f"[debounce] {sender_id}: merged {len(fragments)} messages")

        # Call flush callback
        if self.flush_callback:
            try:
                self.flush_callback(sender_id, merged_text, images)
            except Exception as e:
                log.error(f"[debounce] flush callback error: {e}", exc_info=True)

    def flush_now(self, sender_id: str) -> None:
        """Immediately flush buffer for the given sender."""
        # Cancel pending timer
        with self._lock:
            timer = self._timers.pop(sender_id, None)
        if timer:
            timer.cancel()

        self._flush(sender_id)

    def flush_all(self) -> None:
        """Flush all pending buffers immediately."""
        with self._lock:
            sender_ids = list(self._buffers.keys())

        for sender_id in sender_ids:
            self.flush_now(sender_id)

    def pending_count(self, sender_id: str) -> int:
        """Get the number of pending messages for a sender."""
        with self._lock:
            return len(self._buffers.get(sender_id, []))

    def total_pending(self) -> int:
        """Get total number of pending messages across all senders."""
        with self._lock:
            return sum(len(buf) for buf in self._buffers.values())
