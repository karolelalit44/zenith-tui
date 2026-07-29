"""Direct API test — verify OpenRouter free models respond."""
import asyncio
import os
import sys
import time

# Load keys from .keys file
keys_path = os.path.join(os.path.dirname(__file__), ".keys")
if os.path.isfile(keys_path):
    for line in open(keys_path):
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

import litellm

litellm.drop_params = True

API_KEY = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API")
if not API_KEY:
    print("ERROR: No OpenRouter API key found in .keys or env")
    sys.exit(1)

MODELS = [
    "openrouter/free",
    "cohere/north-mini-code:free",
]

MESSAGES = [
    {"role": "user", "content": "Say hello in one sentence."},
]


async def test_model(model_id: str, litellm_model: str, stream: bool):
    print(f"\n{'='*60}")
    print(f"TEST: model={model_id} litellm={litellm_model} stream={stream}")
    print(f"{'='*60}")
    t0 = time.monotonic()
    try:
        kwargs = {
            "model": litellm_model,
            "messages": MESSAGES,
            "max_tokens": 100,
            "temperature": 0.7,
            "stream": stream,
            "api_base": "https://openrouter.ai/api/v1",
            "api_key": API_KEY,
        }
        print(f"  Kwargs: model={litellm_model} api_base=https://openrouter.ai/api/v1")

        if stream:
            resp = await litellm.acompletion(**kwargs)
            print(f"  Stream opened in {(time.monotonic()-t0)*1000:.0f}ms")
            chunks = 0
            content = ""
            first_chunk_time = None
            async for chunk in resp:
                if first_chunk_time is None:
                    first_chunk_time = time.monotonic()
                    print(f"  First chunk in {(first_chunk_time-t0)*1000:.0f}ms")
                chunks += 1
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    content += delta.content
                    print(f"  Chunk #{chunks}: {delta.content!r}")
            elapsed = (time.monotonic() - t0) * 1000
            print(f"  DONE: {elapsed:.0f}ms, {chunks} chunks, content={content!r}")
        else:
            resp = await litellm.acompletion(**kwargs)
            elapsed = (time.monotonic() - t0) * 1000
            content = resp.choices[0].message.content or ""
            usage = getattr(resp, "usage", None)
            print(f"  DONE: {elapsed:.0f}ms")
            print(f"  Content: {content!r}")
            print(f"  Finish: {getattr(resp.choices[0], 'finish_reason', '?')}")
            if usage:
                print(f"  Usage: prompt={getattr(usage, 'prompt_tokens', '?')} completion={getattr(usage, 'completion_tokens', '?')}")
        return True
    except Exception as e:
        elapsed = (time.monotonic() - t0) * 1000
        print(f"  ERROR after {elapsed:.0f}ms: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    results = {}
    for model_id in MODELS:
        litellm_model = f"openai/{model_id}"
        # Test non-streaming first
        ok = await test_model(model_id, litellm_model, stream=False)
        results[f"{model_id}:complete"] = ok
        # Test streaming
        ok = await test_model(model_id, litellm_model, stream=True)
        results[f"{model_id}:stream"] = ok

    print(f"\n{'='*60}")
    print("RESULTS:")
    for k, v in results.items():
        print(f"  {'PASS' if v else 'FAIL'} {k}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
