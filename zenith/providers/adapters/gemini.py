from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

import aiohttp
import time as _time

from .base import AdapterCapabilities, Chunk, ModelAdapter

logger = logging.getLogger(__name__)


class GeminiAdapter(ModelAdapter):
    name = "gemini"
    capabilities = AdapterCapabilities(streaming=True, thinking=True, function_calling=True, max_output_tokens=8192)

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.7,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = (base_url or "https://generativelanguage.googleapis.com").rstrip("/")
        self.max_tokens = max_tokens
        self.temperature = temperature

    def _endpoint(self, method: str) -> str:
        return f"{self.base_url}/v1beta/models/{self.model}:{method}"

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        contents = []
        system_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                if isinstance(content, str) and content:
                    system_parts.append(content)
                continue
            gemini_role = "model" if role == "assistant" else "user"
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        parts.append({"text": part.get("text", "")})
                    elif isinstance(part, str):
                        parts.append({"text": part})
                if parts:
                    contents.append({"role": gemini_role, "parts": parts})
            elif isinstance(content, str) and content:
                contents.append({"role": gemini_role, "parts": [{"text": content}]})
        if not contents or contents[0].get("role") != "user":
            contents.insert(0, {"role": "user", "parts": [{"text": "Hello"}]})
        self._system_instruction = "\n\n".join(system_parts) if system_parts else None
        return contents

    def _convert_tools(self, tools: list[dict] | None) -> dict | None:
        if not tools:
            return None
        declarations = []
        for tool in tools:
            if tool.get("type") == "function":
                fn = tool.get("function", {})
                declarations.append({
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {"type": "object"}),
                })
        return {"function_declarations": declarations} if declarations else None

    def _extract_parts(self, candidate: dict) -> tuple[str, str, list[dict]]:
        content = candidate.get("content", {})
        parts = content.get("parts", [])
        text_parts = []
        thought_parts = []
        tool_calls = []
        for part in parts:
            if "text" in part:
                if part.get("thought"):
                    thought_parts.append(part["text"])
                else:
                    text_parts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append({
                    "id": fc.get("id", f"call_{fc.get('name', 'unknown')}"),
                    "type": "function",
                    "function": {
                        "name": fc.get("name", ""),
                        "arguments": json.dumps(fc.get("args", {})),
                    },
                })
        return "".join(text_parts), "".join(thought_parts), tool_calls

    async def stream(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[Chunk]:
        logger.info("Gemini stream START model=%s messages=%d tools=%s", self.model, len(messages), len(tools) if tools else 0)
        start_ts = _time.monotonic()
        token_count = 0

        contents = self._convert_messages(messages)
        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": self.max_tokens,
                "temperature": self.temperature,
            },
        }
        if getattr(self, "_system_instruction", None):
            payload["systemInstruction"] = {"parts": [{"text": self._system_instruction}]}
        gemini_tools = self._convert_tools(tools)
        if gemini_tools:
            payload["tools"] = gemini_tools

        url = self._endpoint("generateContent") + f"?key={self.api_key}"
        all_text = ""
        all_thought = ""
        all_tool_calls: list[dict] = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 429:
                        retry_after = 5
                        try:
                            data = await resp.json()
                            retry_msg = data.get("error", {}).get("message", "")
                            if "retry" in retry_msg.lower():
                                import re
                                m = re.search(r"retry in (\d+\.?\d*)s", retry_msg, re.IGNORECASE)
                                if m:
                                    retry_after = float(m.group(1))
                        except Exception:
                            pass
                        logger.warning("Gemini 429, retrying in %.0fs", retry_after)
                        await asyncio.sleep(retry_after)
                        async with aiohttp.ClientSession() as retry_session:
                            async with retry_session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as retry_resp:
                                if retry_resp.status != 200:
                                    err = await retry_resp.text()
                                    logger.error("Gemini retry failed: %s", err[:200])
                                    return
                                resp = retry_resp

                    if resp.status != 200:
                        err = await resp.text()
                        logger.error("Gemini error %d: %s", resp.status, err[:200])
                        return

                    data = await resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text, thought, tcs = self._extract_parts(candidates[0])
                        all_text = text
                        all_thought = thought
                        all_tool_calls = tcs
                        token_count = len(text.split()) + len(thought.split())
        except Exception as e:
            logger.error("Gemini stream error: %s", str(e)[:200])
            return

        if all_thought:
            yield Chunk(content=None, reasoning=all_thought)
        if all_text:
            yield Chunk(content=all_text)
        if all_tool_calls:
            yield Chunk(tool_calls=all_tool_calls)

        elapsed = _time.monotonic() - start_ts
        logger.info("Gemini stream END tokens=%d elapsed=%.2fs", token_count, elapsed)

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        contents = self._convert_messages(messages)
        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": self.max_tokens,
                "temperature": self.temperature,
            },
        }
        if getattr(self, "_system_instruction", None):
            payload["systemInstruction"] = {"parts": [{"text": self._system_instruction}]}
        gemini_tools = self._convert_tools(tools)
        if gemini_tools:
            payload["tools"] = gemini_tools

        url = self._endpoint("generateContent") + f"?key={self.api_key}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    text, _, _ = self._extract_parts(candidates[0])
                    return text
                return ""
