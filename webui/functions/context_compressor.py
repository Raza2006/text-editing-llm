"""
title: Context Compressor
author: Mohammed Raza
description: Keeps each chat within its size limit. When a chat reaches 90% of its limit (or the user pressed Compress), older messages are replaced by a summary before they are sent to the model. Only that chat is affected; the saved history is never changed.
version: 1.0.0
license: Apache-2.0
"""

import asyncio
import hashlib
import json
import os
import threading
import urllib.request

from pydantic import BaseModel, Field

_LOCK = threading.Lock()
DOCUMENT_MARK = "[DOCUMENT]"
SUMMARY_PREFIX = "Summary of the earlier part of this conversation (older messages were condensed to save space):\n"
SUMMARY_INSTRUCTIONS = (
    "You condense conversations between a researcher and an academic editing assistant. "
    "Write a concise summary that preserves: decisions made, the researcher's preferences "
    "(style, spelling, tone, terminology), facts about their paper, and any open tasks. "
    "Do not invent anything. Use plain sentences. Stay under 1500 words."
)
TOO_LONG = (
    "This conversation is too long for the assistant. Please start a new chat, "
    "or paste a shorter part of the document."
)
BUSY = (
    "The assistant could not prepare this long conversation right now (it may be busy). "
    "Please try again in a minute, or start a new chat."
)


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content or "")


def _load_cache(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _update_cache(path, chat_id, **fields):
    with _LOCK:
        cache = _load_cache(path)
        entry = cache.get(chat_id, {})
        entry.update(fields)
        cache[chat_id] = entry
        tmp = path + ".tmp"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        os.replace(tmp, path)


def _digest(messages):
    return hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()


class Filter:
    class Valves(BaseModel):
        llama_url: str = Field(default="http://llama:8080", description="Address of the model server")
        llama_key: str = Field(default="", description="API key of the model server")
        model: str = Field(default="gemma", description="Model used to write summaries")
        per_chat_limit: int = Field(default=262144, description="Largest size of one chat, in tokens")
        compress_at: float = Field(default=0.9, description="Compress at this fraction of the limit")
        keep_recent_turns: int = Field(default=4, description="Recent question/answer pairs kept word for word")
        cache_path: str = Field(default="/app/backend/data/compression_cache.json")

    def __init__(self):
        self.valves = self.Valves()

    # --- model server calls (blocking; run in a worker thread) ---
    def _post(self, path, payload, timeout=900):
        req = urllib.request.Request(
            self.valves.llama_url.rstrip("/") + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.valves.llama_key}"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)

    def _count(self, messages):
        total = 0
        for m in messages:
            total += len(self._post("/tokenize", {"content": _text(m.get("content"))})["tokens"]) + 4
        return total

    def _summarise(self, previous, messages):
        transcript = "\n\n".join(f"{m['role'].upper()}: {_text(m.get('content'))}" for m in messages)
        if previous:
            transcript = f"Earlier summary:\n{previous}\n\nLater messages:\n{transcript}"
        out = self._post("/v1/chat/completions", {
            "model": self.valves.model,
            "messages": [{"role": "system", "content": SUMMARY_INSTRUCTIONS},
                         {"role": "user", "content": transcript}],
            "temperature": 0.2,
            "max_tokens": 2500,
            "chat_template_kwargs": {"enable_thinking": False},
        })
        return out["choices"][0]["message"]["content"].strip()

    # --- main logic ---
    def _process(self, messages, chat_id):
        v = self.valves
        cache = _load_cache(v.cache_path).get(chat_id, {}) if chat_id else {}
        forced = bool(cache.get("force"))
        total = self._count(messages)
        if not forced and total <= v.compress_at * v.per_chat_limit:
            return messages, False

        system = [m for m in messages if m.get("role") == "system"]
        rest = [m for m in messages if m.get("role") != "system"]
        keep_n = max(0, 2 * v.keep_recent_turns)
        recent = rest[-keep_n:] if keep_n else []
        earlier = rest[: len(rest) - len(recent)]
        documents = [m for m in earlier if m.get("role") == "user" and _text(m.get("content")).startswith(DOCUMENT_MARK)]
        older = [m for m in earlier if m not in documents]

        if not older:
            if total > v.per_chat_limit:
                raise Exception(TOO_LONG)
            if chat_id and forced:
                _update_cache(v.cache_path, chat_id, force=False)
            return messages, False

        # Never ask for a summary of more text than the model can read at once:
        # drop the oldest messages until what is summarised fits comfortably.
        budget = int(0.8 * v.per_chat_limit)
        sizes = [self._count([m]) for m in older]
        while len(older) > 1 and sum(sizes) > budget:
            older.pop(0)
            sizes.pop(0)
            cache = {}

        covered = int(cache.get("covered_count", 0))
        if cache.get("summary") and covered <= len(older) and cache.get("covered_hash") == _digest(older[:covered]):
            summary = cache["summary"]
            if covered < len(older):
                summary = self._summarise(summary, older[covered:])
        else:
            summary = self._summarise("", older)

        new_messages = system + [{"role": "system", "content": SUMMARY_PREFIX + summary}] + documents + recent
        if chat_id:
            _update_cache(v.cache_path, chat_id, summary=summary, covered_count=len(older),
                          covered_hash=_digest(older), force=False)
        if self._count(new_messages) > v.per_chat_limit:
            raise Exception(TOO_LONG)
        return new_messages, True

    async def inlet(self, body: dict, __metadata__: dict = None, __event_emitter__=None) -> dict:
        chat_id = (__metadata__ or {}).get("chat_id") or body.get("chat_id")
        messages = body.get("messages") or []
        try:
            new_messages, compressed = await asyncio.to_thread(self._process, messages, chat_id)
        except Exception as e:
            if str(e) in (TOO_LONG, BUSY):
                raise
            raise Exception(BUSY) from e
        if compressed:
            body["messages"] = new_messages
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {
                    "description": "Earlier messages were summarised to keep this chat within its size limit.",
                    "done": True}})
        return body
