"""
Memory System - Three-Stage Pipeline

1. Compress: conversation -> LLM extracts structured memories (key facts + people + time + keywords)
2. Deduplicate: new memory vs existing memories cosine similarity, >threshold skip
3. Retrieve: user message -> embedding -> ChromaDB vector search -> return relevant memories

Storage: ChromaDB (embedded, persistent, no standalone service)
Vectorization: Local BAAI/bge-large-zh via sentence-transformers (1024 dimensions)

Performance:
- Pre-fetch: call prefetch(text) when message arrives (e.g. during debounce) to embed in background
- Embedding cache: TTL-based cache avoids re-embedding identical queries
- Thread pool: reuses threads instead of spawning new ones per request
"""

import json
import logging
import threading
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("agent")

# ============================================================
#  Module State
# ============================================================

_config = {}         # memory config section
_llm_config = {}     # models config (used for calling LLM during compression)
_collection = None   # ChromaDB collection
_enabled = False
_embed_model = None  # sentence-transformers BAAI/bge-large-zh

EMBED_DIMENSION = 1024  # bge-large-zh output dimension

# Embedding pre-fetch / cache
_embed_cache: Dict[str, Tuple[List[float], float]] = {}  # text -> (vector, expiry)
_embed_futures: Dict[str, Future] = {}                   # text -> in-flight Future
_embed_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mem")

EMBED_CACHE_TTL = 120   # seconds to keep a cached vector
EMBED_CACHE_MAX = 256   # max entries to prevent unbounded growth
MIN_RETRIEVE_LEN = 8    # skip memory lookup for very short messages


# ============================================================
#  Public API
# ============================================================


def init(config, llm_config, db_path):
    """Initialize ChromaDB + local bge-large-zh model. Called once at startup."""
    global _config, _llm_config, _collection, _enabled, _embed_model

    mem_cfg = config.get("memory", {})
    if not mem_cfg.get("enabled", False):
        log.info("[memory] disabled in config")
        return

    _config = mem_cfg
    _llm_config = llm_config

    try:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("BAAI/bge-large-zh")
        log.info("[memory] loaded BAAI/bge-large-zh embedding model")
    except Exception as e:
        log.error("[memory] failed to load embedding model: %s" % e)
        return

    try:
        import chromadb
        client = chromadb.PersistentClient(path=db_path)
        # cosine space: distance = 1 - cosine_similarity (lower = more similar)
        _collection = client.get_or_create_collection(
            name="memories",
            metadata={"hnsw:space": "cosine"},
        )
        log.info("[memory] ChromaDB ready, %d memories — db_path=%s" % (_collection.count(), db_path))
        _enabled = True
    except Exception as e:
        log.error("[memory] init failed: %s" % e, exc_info=True)


def prefetch(text: str) -> None:
    """
    Start embedding text in background. Call this as early as possible
    (e.g. when a message arrives, before debounce fires) so the vector
    is ready by the time retrieve() is called.
    """
    if not _enabled or not text or len(text.strip()) < MIN_RETRIEVE_LEN:
        return

    with _embed_lock:
        entry = _embed_cache.get(text)
        if entry and entry[1] > time.time():
            return
        if text in _embed_futures and not _embed_futures[text].done():
            return

        future = _executor.submit(_embed_single, text)
        _embed_futures[text] = future


def retrieve(user_msg: str, _session_key: str = "", top_k: Optional[int] = None) -> str:
    """Retrieve relevant memories, return formatted text block."""
    if not _enabled or not _collection:
        return ""
    if not user_msg or len(user_msg.strip()) < MIN_RETRIEVE_LEN:
        return ""
    if top_k is None:
        top_k = _config.get("retrieve_top_k", 5)

    query_vec = _get_vector(user_msg)
    if not query_vec:
        return ""

    try:
        results = _collection.query(
            query_embeddings=[query_vec],
            n_results=min(top_k, _collection.count()),
            include=["documents", "metadatas"],
        )
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        if not docs:
            return ""

        lines = ["[Relevant Memories]"]
        for fact, meta in zip(docs, metas):
            line = "- " + fact
            ts = (meta or {}).get("timestamp", "")
            if ts:
                line += " (%s)" % ts
            lines.append(line)
        return "\n".join(lines)
    except Exception as e:
        log.error("[memory] retrieve error: %s" % e)
        return ""


def compress_async(evicted_messages, session_key):
    """Start background thread to compress evicted messages into long-term memory."""
    if not _enabled:
        return
    msgs = []
    for m in evicted_messages:
        role = m.get("role", "")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content", "")
        if not content or not isinstance(content, str):
            continue
        if role == "assistant" and m.get("tool_calls"):
            continue
        msgs.append(m)

    if len(msgs) < 2:
        return

    _executor.submit(_compress_worker, msgs, session_key)
    log.info("[memory] compress queued (%d messages)" % len(msgs))


# ============================================================
#  Internal: vector helpers
# ============================================================


def _get_vector(text: str) -> Optional[List[float]]:
    """Return embedding vector, using cache/pre-fetch when available."""
    now = time.time()

    with _embed_lock:
        entry = _embed_cache.get(text)
        if entry and entry[1] > now:
            return entry[0]
        future = _embed_futures.get(text)

    if future and not future.done():
        try:
            return future.result(timeout=6)
        except Exception:
            pass

    return _embed_single(text)


def _embed_single(text: str) -> Optional[List[float]]:
    """Embed a single text, store result in cache."""
    try:
        vecs = _embed([text])
        if not vecs:
            return None
        vec = vecs[0]
        _cache_put(text, vec)
        return vec
    except Exception as e:
        log.error("[memory] embed error: %s" % e)
        return None


def _cache_put(text: str, vec: List[float]) -> None:
    """Store vector in cache, evict oldest entries if over limit."""
    with _embed_lock:
        _embed_futures.pop(text, None)
        if len(_embed_cache) >= EMBED_CACHE_MAX:
            oldest = sorted(_embed_cache.items(), key=lambda x: x[1][1])[:32]
            for k, _ in oldest:
                del _embed_cache[k]
        _embed_cache[text] = (vec, time.time() + EMBED_CACHE_TTL)


# ============================================================
#  Embedding (local BAAI/bge-large-zh via sentence-transformers)
# ============================================================


def _embed(texts: List[str]) -> List[List[float]]:
    """Embed texts using local BAAI/bge-large-zh model."""
    if not texts or _embed_model is None:
        return []
    vecs = _embed_model.encode(texts, normalize_embeddings=True)
    return vecs.tolist()


# ============================================================
#  Compression
# ============================================================

COMPRESS_PROMPT = """You are a memory compressor. Extract structured memories from the following conversation.

Conversation:
{dialogue}

For each piece of valuable information, output a JSON array, each element:
{{
  "fact": "Complete factual statement (resolve pronouns, include timestamps)",
  "keywords": ["keyword1", "keyword2"],
  "persons": ["person names involved"],
  "timestamp": "YYYY-MM-DD HH:MM or null",
  "topic": "topic category"
}}

Rules:
- Only extract information with long-term value (preferences, plans, contacts, decisions, facts)
- Skip chitchat, greetings, repeated confirmations, pure tool call results
- Replace "he/she/I" with specific names (owner = user)
- Replace "tomorrow/next week" with specific dates (infer from conversation time)
- If the conversation has nothing worth remembering, return empty array []
- Output only the JSON array, no other text"""


def _format_messages(messages):
    lines = []
    for m in messages:
        role = "User" if m["role"] == "user" else "Assistant"
        content = m.get("content", "")
        if content:
            lines.append("%s: %s" % (role, content))
    return "\n".join(lines)


def _call_compress_llm(prompt):
    providers = _llm_config.get("providers", {})
    provider = providers.get("deepseek-chat") or providers.get(_llm_config.get("default", ""))
    if not provider:
        log.error("[memory] no LLM provider for compress")
        return []

    url = provider["api_base"].rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": provider["model"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + provider["api_key"],
    })
    with urllib.request.urlopen(req, timeout=provider.get("timeout", 120)) as resp:
        data = json.loads(resp.read())

    content = data["choices"][0]["message"].get("content", "")
    if not content:
        return []

    text = content.strip()
    if text.startswith("```"):
        text = "\n".join(l for l in text.split("\n") if not l.strip().startswith("```"))

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

    log.warning("[memory] compress LLM returned unparseable: %s" % content[:200])
    return []


_NULL_TS = {"null", "none", "n/a", "", "undefined"}

def _clean_ts(value) -> str:
    """Normalize LLM-returned timestamp: reject null-like strings, keep real values."""
    if not value:
        return ""
    s = str(value).strip()
    return "" if s.lower() in _NULL_TS else s


def _compress_worker(messages, session_key):
    """Background: LLM extract -> embed -> deduplicate -> store in ChromaDB"""
    try:
        dialogue = _format_messages(messages)
        if len(dialogue) < 20:
            return

        memories = _call_compress_llm(COMPRESS_PROMPT.format(dialogue=dialogue))
        if not memories:
            log.info("[memory] no memories extracted from %d messages" % len(messages))
            return

        log.info("[memory] extracted %d memories" % len(memories))

        facts = [m.get("fact", "") for m in memories if m.get("fact")]
        if not facts:
            return

        embeddings = _embed(facts)
        if len(embeddings) != len(facts):
            log.error("[memory] embedding count mismatch")
            return

        threshold = _config.get("similarity_threshold", 0.92)
        # cosine distance = 1 - similarity, so distance threshold = 1 - sim_threshold
        dist_threshold = 1.0 - threshold

        ids, vecs, docs, metas = [], [], [], []
        total = _collection.count()

        for mem, vec in zip(memories, embeddings):
            fact = mem.get("fact", "")
            if not fact:
                continue

            # Deduplicate via cosine distance (only when collection has entries)
            if total > 0:
                try:
                    existing = _collection.query(
                        query_embeddings=[vec],
                        n_results=1,
                        include=["distances"],
                    )
                    distances = existing.get("distances", [[]])[0]
                    if distances and distances[0] < dist_threshold:
                        sim = 1.0 - distances[0]
                        log.info("[memory] skip duplicate (sim=%.3f): %s" % (sim, fact[:50]))
                        continue
                except Exception:
                    pass

            ids.append(str(uuid.uuid4()))
            vecs.append(vec)
            docs.append(fact)
            metas.append({
                "keywords": json.dumps(mem.get("keywords", []), ensure_ascii=False),
                "persons": json.dumps(mem.get("persons", []), ensure_ascii=False),
                "timestamp": _clean_ts(mem.get("timestamp")),
                "topic": mem.get("topic", ""),
                "session_key": session_key,
                "created_at": time.time(),
            })

        if ids:
            _collection.add(ids=ids, embeddings=vecs, documents=docs, metadatas=metas)
            total += len(ids)
            log.info("[memory] stored %d new memories (skipped %d duplicates)" % (
                len(ids), len(facts) - len(ids)))
        else:
            log.info("[memory] all %d memories were duplicates" % len(facts))

    except Exception as e:
        log.error("[memory] compress error: %s" % e, exc_info=True)
