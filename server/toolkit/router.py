from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class IntentKind(str, Enum):
    DIRECT_RESPONSE = "direct_response"
    READ_ONLY_DISCOVERY = "read_only_discovery"
    EXECUTION_MUTATION = "execution_mutation"


@dataclass
class IntentClassification:
    kind: IntentKind
    confidence: float
    reason: str


_GREETING_RE = re.compile(
    r"^(hi|hello|hey|greetings|howdy|who are you|what can you do|good morning|good evening|good afternoon)[\s!?.]*$",
    re.IGNORECASE,
)

_MUTATION_RE = re.compile(
    r"\b(build|fix|add|update|delete|create|change|modify|remove|run|test|execute|install|commit|refactor|write)\b",
    re.IGNORECASE,
)

_DISCOVERY_RE = re.compile(
    r"\b(find|search|where|locate|grep|look for|show me|list|view|read|inspect)\b",
    re.IGNORECASE,
)


class IntentRouter:
    def __init__(self, high_confidence_threshold: float = 0.85) -> None:
        self.high_confidence_threshold = high_confidence_threshold

    def classify(self, user_prompt: str, mode: str = "build") -> IntentClassification:
        prompt_strip = user_prompt.strip()
        if not prompt_strip:
            return IntentClassification(
                kind=IntentKind.DIRECT_RESPONSE,
                confidence=1.0,
                reason="Empty prompt",
            )

        # 1. Check greeting pattern
        if _GREETING_RE.match(prompt_strip):
            return IntentClassification(
                kind=IntentKind.DIRECT_RESPONSE,
                confidence=1.0,
                reason="Matched direct conversational greeting",
            )

        # 2. Check explicit mutation intent
        if _MUTATION_RE.search(prompt_strip):
            return IntentClassification(
                kind=IntentKind.EXECUTION_MUTATION,
                confidence=0.95,
                reason="Matched workspace mutation or command execution keywords",
            )

        # 3. Check explicit discovery intent
        if _DISCOVERY_RE.search(prompt_strip):
            return IntentClassification(
                kind=IntentKind.READ_ONLY_DISCOVERY,
                confidence=0.85,
                reason="Matched workspace exploration or inspection keywords",
            )

        # Default fallback classification
        return IntentClassification(
            kind=IntentKind.EXECUTION_MUTATION
            if mode == "build"
            else IntentKind.READ_ONLY_DISCOVERY,
            confidence=0.7,
            reason="Default mode-based intent classification",
        )
