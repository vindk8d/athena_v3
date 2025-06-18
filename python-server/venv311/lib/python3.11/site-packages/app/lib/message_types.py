from typing import Any

from langchain_core.messages import FunctionMessage, ToolMessage


class LiberalFunctionMessage(FunctionMessage):
    content: Any

    def get(self, key, default=None):
        return getattr(self, key, default)


class LiberalToolMessage(ToolMessage):
    content: Any

    def get(self, key, default=None):
        return getattr(self, key, default)
