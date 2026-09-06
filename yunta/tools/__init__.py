import json
from dataclasses import dataclass

from ..api import ToolDef


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    fn: callable
    requires_approval: bool = False


class Registry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, description: str, parameters: dict, requires_approval: bool = False):
        def deco(fn):
            self._tools[name] = Tool(name, description, parameters, fn, requires_approval)
            return fn

        return deco

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def definitions(self) -> list[ToolDef]:
        return [
            ToolDef(name=t.name, description=t.description, parameters=t.parameters)
            for t in self._tools.values()
        ]


registry = Registry()


def _parse(raw: str) -> dict:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
