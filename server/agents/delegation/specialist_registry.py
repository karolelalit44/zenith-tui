"""Capability routing: which specialist owns this prompt?

Scoring is deterministic and explainable:

- capability tokens found in the prompt (stem-tolerant prefix match) score
  +3 for a full capability hit, +1 for a partial one;
- ``best_for`` phrases score +2 when all content words match, +1 partial;
- any fully-matched ``avoid_for`` phrase vetoes the agent outright.

A route only exists at or above ``MIN_CAPABILITY_SCORE``.
"""

from __future__ import annotations

import re

from .agent_definition import AgentDefinition

MIN_CAPABILITY_SCORE = 3

_WORD_RE = re.compile(r"[a-z]+")
_STOPWORDS = {
    "x",
    "y",
    "does",
    "do",
    "is",
    "are",
    "the",
    "a",
    "an",
    "to",
    "of",
    "how",
    "where",
    "what",
    "now",
}


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _matches(word: str, vocab: set[str]) -> bool:
    w = word.rstrip("s")
    if w in vocab:
        return True
    if len(w) < 5:
        return False
    for v in vocab:
        v = v.rstrip("s")
        if len(v) >= 5 and (w.startswith(v[:5]) or v.startswith(w[:5])):
            return True
    return False


def _phrase_words(phrase: str) -> list[str]:
    return [w for w in _WORD_RE.findall(phrase.lower()) if w not in _STOPWORDS]


def _phrase_hit(phrase: str, words: set[str]) -> int:
    parts = _phrase_words(phrase)
    if not parts:
        return 0
    hits = sum(1 for p in parts if _matches(p, words))
    if hits == len(parts):
        return 2
    if hits:
        return 1
    return 0


def score_prompt(prompt: str, definition: AgentDefinition) -> int:
    """Capability-fit score for ``prompt``; 0 means no signal."""
    words = _words(prompt)
    score = 0
    for capability in definition.capabilities:
        parts = _phrase_words(capability.replace("_", " "))
        hits = sum(1 for p in parts if _matches(p, words))
        if hits == len(parts):
            score += 3
        elif hits:
            score += 1
    for phrase in definition.best_for:
        score += _phrase_hit(phrase, words)
    return score


def avoid_match(prompt: str, definition: AgentDefinition) -> bool:
    words = _words(prompt)
    for phrase in definition.avoid_for:
        parts = _WORD_RE.findall(phrase.lower())
        if parts and all(_matches(p, words) for p in parts):
            return True
    return False


class SpecialistRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentDefinition] = {}

    @classmethod
    def default(cls) -> SpecialistRegistry:
        from .agent_definition import CodebaseScout

        registry = cls()
        registry.register(CodebaseScout)
        return registry

    def register(self, definition: AgentDefinition) -> None:
        self._agents[definition.id] = definition

    def get(self, agent_id: str) -> AgentDefinition | None:
        return self._agents.get(agent_id)

    def all(self) -> list[AgentDefinition]:
        return list(self._agents.values())

    def best_for(self, agent_id: str) -> list[str]:
        agent = self.get(agent_id)
        return list(agent.best_for) if agent else []

    def avoid_for(self, agent_id: str) -> list[str]:
        agent = self.get(agent_id)
        return list(agent.avoid_for) if agent else []

    def route(self, prompt: str) -> AgentDefinition | None:
        best: AgentDefinition | None = None
        best_score = 0
        for definition in self._agents.values():
            if avoid_match(prompt, definition):
                continue
            s = score_prompt(prompt, definition)
            if s > best_score:
                best, best_score = definition, s
        if best is None or best_score < MIN_CAPABILITY_SCORE:
            return None
        return best
