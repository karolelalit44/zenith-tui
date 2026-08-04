
from __future__ import annotations
import logging
from dataclasses import dataclass
from server.config.settings import AppSettings
from server.domain.message import Message
from server.persistence.repositories import load_catalog
from server.providers.token_counter import TokenCounter

logger = logging.getLogger(__name__)

SUMMARY_FRAMING_TOKENS = 4


def _prompt_buffer(system_prompt: str) -> int:
    estimated = max(200, len(system_prompt) // 10)
    return min(estimated, 2000)


def _get_model_context_window(model: str, fallback: int = 128000) -> int:
    try:
        cat = load_catalog()
        for prov in cat.get("providers", {}).values():
            for m in prov.get("models", []):
                if m["id"] == model:
                    return m.get("context_window", fallback)
    except Exception:
        pass
    return fallback


def _adaptive_reserve(model: str, context_window: int) -> int:
    if context_window >= 200000:
        return min(20000, context_window // 10)
    return max(4096, context_window // 5)


def _adaptive_summary_threshold(model: str, context_window: int) -> float:
    if context_window >= 200000:
        return 0.85
    if context_window >= 32000:
        return 0.80
    return 0.75


@dataclass
class TokenInfo:
    used: int
    remaining: int
    total: int
    percent: float


_REPO_MAP_INSTANCES: dict[str, object] = {}


def _get_repo_map_instance(workspace_root: str, refresh: str = "files"):
    key = f"{workspace_root}|{refresh}"
    repo = _REPO_MAP_INSTANCES.get(key)
    if repo is None:
        from server.workspace.repo_map import RepoMap

        repo = RepoMap(workspace_root, refresh=refresh)
        _REPO_MAP_INSTANCES[key] = repo
    return repo


class ContextManager:

    def __init__(self, config: AppSettings) -> None:
        self.config = config
        self.token_counter = TokenCounter()
        self._repo_map_cache: str | None = None
        self._memory_cache: str | None = None

    def _resolve_context_window(self, model: str) -> int:
        from_catalog = _get_model_context_window(model)
        return min(from_catalog, self.config.max_context_tokens)

    def _resolve_repo_map_tokens(self, model: str) -> int:
        if self.config.repo_map_tokens is not None:
            return self.config.repo_map_tokens
        ctx = self._resolve_context_window(model)
        return min(1024, max(400, ctx // 32))

    def get_repo_map(self, chat_files: list[str] | None = None, model: str = "cl100k_base") -> str:
        if not self.config.repo_map_enabled:
            return ""
        if self._repo_map_cache is not None:
            return self._repo_map_cache
        try:
            repo = _get_repo_map_instance(self.config.workspace_root, refresh="files")
            self._repo_map_cache = repo.get_repo_map(chat_files=chat_files, max_tokens=self._resolve_repo_map_tokens(model))
        except Exception as e:
            logger.warning("Failed to build repo map: %s", e)
            self._repo_map_cache = ""
        return self._repo_map_cache

    def get_memory(self) -> str:
        if not self.config.memory_enabled:
            return ""
        if self._memory_cache is not None:
            return self._memory_cache
        try:
            from server.sessions.memory import MemoryStore

            self._memory_cache = MemoryStore(self.config.workspace_root).load()
        except Exception as e:
            logger.warning("Failed to load memory: %s", e)
            self._memory_cache = ""
        return self._memory_cache

    def _compute_code_relevance(self, prompt: str, history: list[Message] | None = None) -> float:
        if not prompt:
            return 0.0

        p_lower = prompt.lower()
        score = 0.0

        if any(ext in p_lower for ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".css", ".html", ".go", ".rs", ".c", ".cpp", ".h", ".toml", ".sql", ".sh")):
            score += 0.5

        if "/" in prompt or "\\" in prompt:
            score += 0.3

        code_keywords = ("code", "file", "function", "class", "def ", "const ", "let ", "var ", "interface", "type ", "bug", "fix", "refactor", "test", "pytest", "error", "exception", "traceback", "import", "export", "return", "git", "commit", "build", "compile", "script", "server", "api", "tui", "repo")
        if any(kw in p_lower for kw in code_keywords):
            score += 0.3

        if "`" in prompt or "```" in prompt or "{" in prompt or "==" in prompt:
            score += 0.4

        if history:
            recent_text = " ".join(m.content.lower() for m in history[-3:] if hasattr(m, "content") and m.content)
            if any(ext in recent_text for ext in (".py", ".ts", ".tsx", ".js", "error", "traceback")):
                score += 0.2

        return min(1.0, score)

    def build_messages(self, history: list[Message], system_prompt: str, new_prompt: str, model: str, summary: str | None = None, plan_block: str | None = None, use_system_prompt: bool = True, repo_map: str | None = None, memory: str | None = None) -> list[dict]:
        max_tokens = self._resolve_context_window(model)
        reserve = _adaptive_reserve(model, max_tokens)
        budget = max_tokens - reserve

        messages: list[dict] = []
        pbuf = _prompt_buffer(system_prompt)

        repo_map_text = repo_map if repo_map is not None else ""

        repo_map_block = (f"<repo_map>\n{repo_map_text}\n</repo_map>" if repo_map_text.strip() else "")
        repo_map_tokens = self.token_counter.count(repo_map_block, model) if repo_map_block else 0

        memory_text = memory if memory is not None else self.get_memory()
        memory_block = f"<memory>\n{memory_text}\n</memory>" if memory_text.strip() else ""
        memory_tokens = self.token_counter.count(memory_block, model) if memory_block else 0

        if use_system_prompt:
            system_tokens = self.token_counter.count(system_prompt, model)
            messages.append({"role": "system", "content": system_prompt})
            used = system_tokens
        else:
            used = 0

        memory_injected = False
        if use_system_prompt:
            if repo_map_block:
                messages.append({"role": "system", "content": repo_map_block})
                used += repo_map_tokens
                logger.info("Repo map injected into context: %d chars, %d tokens", len(repo_map_text), repo_map_tokens)
            if memory_block and used + memory_tokens + pbuf <= budget:
                messages.append({"role": "system", "content": memory_block})
                used += memory_tokens
                memory_injected = True
                logger.info("Memory injected into context: %d chars, %d tokens", len(memory_text), memory_tokens)
            elif memory_block:
                logger.warning("Memory block too large to inject (%d tokens, budget %d)", memory_tokens, budget)
        else:
            used += repo_map_tokens
            if memory_block and used + memory_tokens + pbuf <= budget:
                used += memory_tokens
                memory_injected = True
            elif memory_block:
                logger.warning("Memory block too large to inject (%d tokens, budget %d)", memory_tokens, budget)

        if plan_block:
            plan_tokens = self.token_counter.count(plan_block, model)
            if used + plan_tokens + pbuf <= budget:
                messages.append({"role": "system", "content": f"<plan_to_execute>\n{plan_block}\n</plan_to_execute>\n\nYou MUST execute the plan above exactly. Create every file listed, implement every component, and follow the architecture decisions described."})
                used += plan_tokens
                logger.info("Plan block injected into context: %d chars, %d tokens", len(plan_block), plan_tokens)
            else:
                logger.warning("Plan block too large to inject (%d tokens, budget %d)", plan_tokens, budget)

        if summary:
            summary_tokens = self.token_counter.count(summary, model)
            if used + summary_tokens <= budget:
                messages.append({"role": "user", "content": f"[Previous conversation summary]\n{summary}"})
                messages.append({"role": "assistant", "content": "Understood."})
                used += summary_tokens + SUMMARY_FRAMING_TOKENS

        history_msgs: list[tuple[dict, int]] = []
        last_key: tuple[str, str] | None = None
        for msg in history:
            if msg.role == "assistant" and not msg.content and not msg.has_tool_calls:
                continue
            key = (msg.role, msg.content)
            if key == last_key:
                continue
            last_key = key
            entry = {"role": msg.role, "content": msg.content}
            entry_tokens = self.token_counter.count(msg.content, model)
            history_msgs.append((entry, entry_tokens))

        included: list[tuple[dict, int]] = []
        for entry, tokens in reversed(history_msgs):
            if used + tokens + pbuf > budget:
                break
            included.append((entry, tokens))
            used += tokens

        while included and included[-1][0]["role"] == "tool":
            _, tokens = included.pop()
            used -= tokens

        messages.extend(entry for entry, _ in reversed(included))

        if not use_system_prompt:
            parts = [system_prompt]
            if repo_map_block:
                parts.append(repo_map_block)
            if memory_injected:
                parts.append(memory_block)
            parts.append(new_prompt)
            new_entry = {"role": "user", "content": "\n\n".join(parts)}
        else:
            new_entry = {"role": "user", "content": new_prompt}

        if not messages or messages[-1].get("content") != new_entry.get("content"):
            messages.append(new_entry)

        return messages

    def should_summarize(self, messages: list[dict], model: str, provider=None) -> bool:
        used = self.usage_tokens(messages, model, provider)
        max_tokens = self._resolve_context_window(model)
        threshold = max_tokens * _adaptive_summary_threshold(model, max_tokens)
        reserve = _adaptive_reserve(model, max_tokens)
        return used >= threshold or used >= max_tokens - reserve

    def get_token_info(self, messages: list[dict], model: str, provider=None) -> TokenInfo:
        used = self.usage_tokens(messages, model, provider)
        total = self._resolve_context_window(model)
        remaining = max(0, total - used)
        percent = used / total if total > 0 else 0.0
        return TokenInfo(used=used, remaining=remaining, total=total, percent=percent)

    def usage_tokens(self, messages: list[dict], model: str, provider=None) -> int:
        if provider is not None:
            cum = getattr(provider, "_cumulative_usage", None) or {}
            reported = int(cum.get("total_tokens") or 0)
            if reported > 0:
                return reported
        return self.token_counter.count_messages(messages, model)

    def count_tokens(self, text: str, model: str) -> int:
        return self.token_counter.count(text, model)
