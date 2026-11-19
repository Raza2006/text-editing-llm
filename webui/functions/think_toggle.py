"""
title: Think
author: Mohammed Raza
description: When switched on for a chat, the model thinks step by step before answering. Slower, but deeper. Off by default.
version: 1.0.0
license: Apache-2.0
"""

from pydantic import BaseModel


class Filter:
    class Valves(BaseModel):
        pass

    def __init__(self):
        self.valves = self.Valves()
        self.toggle = True
        self.icon = (
            "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAy"
            "NCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJjdXJyZW50Q29sb3IiIHN0cm9rZS13aWR0aD0iMS41Ij48cGF0aCBkPSJNOSAxOGg2TTEwIDIx"
            "aDRNMTIgM2E2IDYgMCAwIDAtMy41IDEwLjljLjYuNCAxIDEgMSAxLjdWMTZoNXYtLjRjMC0uNy40LTEuMyAxLTEuN0E2IDYgMCAwIDAg"
            "MTIgM3oiLz48L3N2Zz4="
        )

    async def inlet(self, body: dict, **kwargs) -> dict:
        body.setdefault("chat_template_kwargs", {})["enable_thinking"] = True
        return body
