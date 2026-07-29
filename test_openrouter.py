"""Manual debug script for OpenRouter provider.

Tests the API at multiple levels to isolate where the error occurs.
Usage:
    python test_openrouter.py
"""

import asyncio
import os
import sys
import time
import traceback

API_KEY = "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"
BASE_URL = "https://openrouter.ai/api/v1"

# Models to test
MODELS = [
    "cohere/north-mini-code:free",
    "openrouter/free",
    "gryphe/mythomax-l2-13b:free",
]


async def test_raw_httpx(model: str):
    """Test 1: Raw HTTP call via httpx (no LiteLLM)."""
    print(f"\n{'='*60}")
    print(f"[TEST 1] Raw httpx — model={model}")
    print(f"{'='*60}")
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "Say OK"}],
                "max_tokens": 50,
                "temperature": 0.7,
                "stream": False,
            }
            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8765",
                "X-Title": "Zenith Test",
            }
            t0 = time.monotonic()
            resp = await client.post(
                f"{BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )
            elapsed = (time.monotonic() - t0) * 1000
            body = resp.text
            print(f"  Status: {resp.status_code}")
            print(f"  Elapsed: {elapsed:.0f}ms")
            print(f"  Headers: {dict(resp.headers)}")
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                print(f"  Content: {content[:200]!r}")
                print(f"  Usage: {usage}")
                print("  ✓ SUCCESS")
                return True
            else:
                print(f"  Body: {body[:500]}")
                print("  ✗ FAILED")
                return False
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        return False


async def test_litellm_direct(model: str):
    """Test 2: LiteLLM direct call (no project code)."""
    print(f"\n{'='*60}")
    print(f"[TEST 2] LiteLLM direct — model={model}")
    print(f"{'='*60}")
    try:
        os.environ["OPENROUTER_API_KEY"] = API_KEY
        import litellm

        litellm.drop_params = True

        t0 = time.monotonic()
        response = await litellm.acompletion(
            model=f"openai/{model}",
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=50,
            temperature=0.7,
            api_base=BASE_URL,
            api_key=API_KEY,
        )
        elapsed = (time.monotonic() - t0) * 1000
        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        print(f"  Elapsed: {elapsed:.0f}ms")
        print(f"  Content: {content[:200]!r}")
        print(f"  Usage: {usage}")
        print(f"  Finish: {response.choices[0].finish_reason}")
        print("  ✓ SUCCESS")
        return True
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        return False


async def test_litellm_stream(model: str):
    """Test 3: LiteLLM streaming."""
    print(f"\n{'='*60}")
    print(f"[TEST 3] LiteLLM stream — model={model}")
    print(f"{'='*60}")
    try:
        os.environ["OPENROUTER_API_KEY"] = API_KEY
        import litellm

        litellm.drop_params = True

        t0 = time.monotonic()
        stream = await litellm.acompletion(
            model=f"openai/{model}",
            messages=[{"role": "user", "content": "Say OK and nothing else"}],
            max_tokens=50,
            temperature=0.7,
            api_base=BASE_URL,
            api_key=API_KEY,
            stream=True,
        )
        chunks = []
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                chunks.append(delta.content)
        elapsed = (time.monotonic() - t0) * 1000
        content = "".join(chunks)
        print(f"  Elapsed: {elapsed:.0f}ms")
        print(f"  Chunks: {len(chunks)}")
        print(f"  Content: {content[:200]!r}")
        print("  ✓ SUCCESS")
        return True
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        return False


async def test_project_llm_provider(model: str):
    """Test 4: Using the project's own LLMProvider class."""
    print(f"\n{'='*60}")
    print(f"[TEST 4] Project LLMProvider — model={model}")
    print(f"{'='*60}")
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        os.environ["OPENROUTER_API_KEY"] = API_KEY

        from providers.llm_provider import LLMProvider

        provider = LLMProvider(
            name="openrouter",
            model=model,
            api_key=API_KEY,
            base_url=BASE_URL,
        )
        print(f"  LiteLLM model: {provider._litellm_model}")

        t0 = time.monotonic()
        content = await provider.complete([{"role": "user", "content": "Say OK"}])
        elapsed = (time.monotonic() - t0) * 1000
        print(f"  Elapsed: {elapsed:.0f}ms")
        print(f"  Content: {content[:200]!r}")
        print("  ✓ SUCCESS")
        return True
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        return False


async def test_project_llm_provider_stream(model: str):
    """Test 5: Using the project's LLMProvider streaming."""
    print(f"\n{'='*60}")
    print(f"[TEST 5] Project LLMProvider stream — model={model}")
    print(f"{'='*60}")
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        os.environ["OPENROUTER_API_KEY"] = API_KEY

        from providers.llm_provider import LLMProvider

        provider = LLMProvider(
            name="openrouter",
            model=model,
            api_key=API_KEY,
            base_url=BASE_URL,
        )

        t0 = time.monotonic()
        chunks = []
        async for content, reasoning in provider.stream([{"role": "user", "content": "Say OK and nothing else"}]):
            if content:
                chunks.append(content)
        elapsed = (time.monotonic() - t0) * 1000
        content = "".join(chunks)
        print(f"  Elapsed: {elapsed:.0f}ms")
        print(f"  Chunks: {len(chunks)}")
        print(f"  Content: {content[:200]!r}")
        print("  ✓ SUCCESS")
        return True
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        return False


async def test_with_tools(model: str):
    """Test 6: API call with tools (this was the failing case)."""
    print(f"\n{'='*60}")
    print(f"[TEST 6] With tools — model={model}")
    print(f"{'='*60}")
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        os.environ["OPENROUTER_API_KEY"] = API_KEY

        from providers.llm_provider import LLMProvider

        provider = LLMProvider(
            name="openrouter",
            model=model,
            api_key=API_KEY,
            base_url=BASE_URL,
        )

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file from the filesystem",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "The file path"}
                        },
                        "required": ["path"],
                    },
                },
            }
        ]

        messages = [
            {"role": "user", "content": "List the files in the current directory using glob tool"},
        ]

        t0 = time.monotonic()
        content = await provider.complete(messages, tools=tools)
        elapsed = (time.monotonic() - t0) * 1000
        print(f"  Elapsed: {elapsed:.0f}ms")
        print(f"  Content: {content[:300]!r}")
        if provider._last_native_tool_calls:
            print(f"  Tool calls: {[(tc['function']['name'], tc['function']['arguments'][:200]) for tc in provider._last_native_tool_calls]}")
        print("  ✓ SUCCESS")
        return True
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        return False


async def test_validate_provider(model: str):
    """Test 7: Validation endpoint simulation."""
    print(f"\n{'='*60}")
    print(f"[TEST 7] Validate provider — model={model}")
    print(f"{'='*60}")
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        os.environ["OPENROUTER_API_KEY"] = API_KEY

        from providers.llm_provider import LLMProvider

        provider = LLMProvider(
            name="openrouter",
            model=model,
            api_key=API_KEY,
            base_url=BASE_URL,
        )

        t0 = time.monotonic()
        valid = await provider.validate()
        elapsed = (time.monotonic() - t0) * 1000
        print(f"  Elapsed: {elapsed:.0f}ms")
        print(f"  Valid: {valid}")
        if valid:
            print("  ✓ SUCCESS")
        else:
            print("  ✗ FAILED")
        return valid
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        return False


async def main():
    print(f"OpenRouter API Key: {API_KEY[:15]}...{API_KEY[-8:]}")
    print(f"Base URL: {BASE_URL}")
    print(f"Models to test: {MODELS}")

    for model in MODELS:
        print(f"\n{'#'*60}")
        print(f"# TESTING MODEL: {model}")
        print(f"{'#'*60}")

        await test_raw_httpx(model)
        await test_litellm_direct(model)
        await test_litellm_stream(model)
        await test_project_llm_provider(model)
        await test_project_llm_provider_stream(model)
        await test_with_tools(model)
        await test_validate_provider(model)


if __name__ == "__main__":
    asyncio.run(main())
