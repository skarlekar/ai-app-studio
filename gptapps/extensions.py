"""Trusted, explicitly loaded Python extensions; never loaded from imported text."""
import importlib
from dataclasses import dataclass
from typing import Callable


@dataclass
class FunctionTool:
    name: str
    description: str
    parameters: dict
    handler: Callable
    read_only: bool = True

    def declaration(self):
        return {"type": "function", "name": self.name, "description": self.description,
                "parameters": self.parameters, "strict": True}


class Registry:
    def __init__(self):
        self.tools = {}

    def add(self, tool):
        if not isinstance(tool, FunctionTool) or tool.name in self.tools:
            raise ValueError("Expected a uniquely named FunctionTool")
        self.tools[tool.name] = tool

    def load(self, reference):
        module, function = reference.split(":", 1)
        getattr(importlib.import_module(module), function)(self)


def scoring_example(registry):
    """Example pure-code tool. It does not call Embeddings or score images."""
    import math

    def cosine_score(left, right):
        if len(left) != len(right) or not left:
            raise ValueError("Vectors must be nonempty and have equal length")
        values = left + right
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in values):
            raise ValueError("Vectors must contain finite numbers")
        norm = math.sqrt(sum(x*x for x in left)) * math.sqrt(sum(x*x for x in right))
        if not norm:
            raise ValueError("Zero vectors have no cosine similarity")
        score = max(-1.0, min(1.0, sum(a*b for a, b in zip(left, right))/norm))
        return {"cosine": score, "percentage": (score+1)*50}

    registry.add(FunctionTool("cosine_score", "Calculate cosine similarity of two supplied vectors.",
        {"type": "object", "properties": {"left": {"type": "array", "items": {"type": "number"}},
         "right": {"type": "array", "items": {"type": "number"}}},
         "required": ["left", "right"], "additionalProperties": False}, cosine_score))
