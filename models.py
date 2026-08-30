from dataclasses import dataclass
from typing import Literal


Category = Literal[
    "safe",
    "advertising",
    "insult",
    "nsfw",
    "violence",
    "drugs",
]


@dataclass
class ModerationResult:
    category: Category
    confidence: float
    action: str
    reason: str
    source: str = "llm"
