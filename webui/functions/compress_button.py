"""
title: Compress chat
author: Mohammed Raza
description: A button under replies. Marks this chat so that its older messages are summarised before your next message is sent.
version: 1.0.0
license: Apache-2.0
"""

import json
import os
import threading

from pydantic import BaseModel, Field

_LOCK = threading.Lock()


def _update_cache(path, chat_id, **fields):
    with _LOCK:
        try:
            with open(path, encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, ValueError):
            cache = {}
        entry = cache.get(chat_id, {})
        entry.update(fields)
        cache[chat_id] = entry
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        os.replace(tmp, path)


class Action:
    class Valves(BaseModel):
        cache_path: str = Field(default="/app/backend/data/compression_cache.json")

    def __init__(self):
        self.valves = self.Valves()

    async def action(self, body: dict, __event_emitter__=None, **kwargs):
        chat_id = body.get("chat_id")
        if not chat_id:
            return None
        _update_cache(self.valves.cache_path, chat_id, force=True)
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {
                "description": "This chat will be compressed before your next message.", "done": True}})
        return None
