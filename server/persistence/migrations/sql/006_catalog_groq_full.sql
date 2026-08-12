-- 006: expand groq catalog to the full chat-capable model list
--
-- Adds the remaining chat-capable Groq models that were missing from the
-- original seed (004): openai/gpt-oss-safeguard-20b, groq/compound,
-- groq/compound-mini, allam-2-7b, meta-llama/llama-prompt-guard-2-22m,
-- meta-llama/llama-prompt-guard-2-86m. Non-chat audio/speech models
-- (whisper-*, canopylabs/orpheus-*) are intentionally excluded.
--
-- Idempotent: upserts the full groq model set so existing databases converge
-- to the same catalog as a fresh seed.

INSERT INTO catalog_models (provider_id, id, name, description, context_window, parameters, architecture, input_modalities, output_modalities, tags, model_capabilities_json, speed_tier, best_for, pricing_json, is_default, tokenizer, prompt_tier) VALUES
    ('groq', 'llama-3.3-70b-versatile', 'Llama 3.3 70B Versatile', 'Meta''s 70B. Best Groq model — fast (1.3s avg), excellent tool calling, 10/10 benchmark. Default choice.', 128000, '70B', 'Dense Transformer', '["text"]', '["text"]', '["high-quality", "production", "coding", "default"]', '{"function_calling": true, "structured_output": true, "reasoning": false, "thinking": false}', 'fast', '["agentic coding", "complex tasks", "general purpose"]', '{"input": 0.0, "output": 0.0}', 1, '', 'flagship'),
    ('groq', 'llama-3.1-8b-instant', 'Llama 3.1 8B Instant', 'Meta''s 8B. Ultra-fast (1.7s), generous rate limits (14.4K RPD).', 131072, '8B', 'Dense Transformer', '["text"]', '["text"]', '["ultra-fast", "lightweight", "production"]', '{"function_calling": true, "structured_output": true, "reasoning": false, "thinking": false}', 'fast', '["quick responses", "simple coding", "batch processing"]', '{"input": 0.0, "output": 0.0}', 0, '', 'compact'),
    ('groq', 'openai/gpt-oss-20b', 'GPT OSS 20B', 'OpenAI''s open-source 20B. Best value — fast (1.6s) + high quality + clean tool calls. 10/10 benchmark.', 131072, '20B', 'Dense Transformer', '["text"]', '["text"]', '["openai", "production", "coding", "best-value"]', '{"function_calling": true, "structured_output": true, "reasoning": false, "thinking": false}', 'fast', '["general coding", "agentic workflows", "best bang-for-buck"]', '{"input": 0.0, "output": 0.0}', 0, '', 'flagship'),
    ('groq', 'openai/gpt-oss-120b', 'GPT OSS 120B', 'OpenAI''s largest open-source model. Highest quality among GPT OSS (6.2s avg). Best tool calling.', 131072, '120B', 'Dense Transformer', '["text"]', '["text"]', '["openai", "high-quality", "production"]', '{"function_calling": true, "structured_output": true, "reasoning": false, "thinking": false}', 'moderate', '["complex coding", "agentic workflows", "high-quality output"]', '{"input": 0.0, "output": 0.0}', 0, '', 'flagship'),
    ('groq', 'qwen/qwen3.6-27b', 'Qwen 3.6 27B', 'Alibaba''s 27B. Reasoning support. Slow (7.8s avg), outputs thinking tags in responses. Good tool calling.', 131072, '27B', 'Dense Transformer', '["text"]', '["text"]', '["reasoning", "preview", "slow-inference"]', '{"function_calling": true, "structured_output": true, "reasoning": true, "thinking": false}', 'slow', '["reasoning tasks", "analysis", "complex coding"]', '{"input": 0.0, "output": 0.0}', 0, '', 'flagship'),
    ('groq', 'openai/gpt-oss-safeguard-20b', 'Safety GPT OSS 20B', 'OpenAI''s open-source 20B safety-tuned model. Same architecture as GPT OSS 20B with safety guardrails.', 131072, '20B', 'Dense Transformer', '["text"]', '["text"]', '["openai", "production", "safety"]', '{"function_calling": true, "structured_output": true, "reasoning": true, "thinking": false}', 'fast', '["general coding", "agentic workflows", "safety-sensitive tasks"]', '{"input": 0.0, "output": 0.0}', 0, '', 'flagship'),
    ('groq', 'groq/compound', 'Compound', 'Groq''s in-house flagship. Ultra-fast inference on LPU.', 131072, 'unknown', 'Dense Transformer', '["text"]', '["text"]', '["production", "fast", "groq"]', '{"function_calling": false, "structured_output": true, "reasoning": false, "thinking": false}', 'fast', '["quick responses", "general purpose", "lightweight"]', '{"input": 0.0, "output": 0.0}', 0, '', 'flagship'),
    ('groq', 'groq/compound-mini', 'Compound Mini', 'Groq''s compact in-house model. Even faster, low-latency responses.', 131072, 'unknown', 'Dense Transformer', '["text"]', '["text"]', '["production", "ultra-fast", "lightweight", "groq"]', '{"function_calling": false, "structured_output": true, "reasoning": false, "thinking": false}', 'fast', '["quick responses", "batch processing", "simple tasks"]', '{"input": 0.0, "output": 0.0}', 0, '', 'compact'),
    ('groq', 'allam-2-7b', 'ALLaM-2-7b', 'SDAIA''s bilingual Arabic/English 7B model. Strong for Arabic-language tasks.', 4096, '7B', 'Dense Transformer', '["text"]', '["text"]', '["production", "bilingual", "arabic"]', '{"function_calling": false, "structured_output": true, "reasoning": false, "thinking": false}', 'fast', '["arabic text", "translation", "quick responses"]', '{"input": 0.0, "output": 0.0}', 0, '', 'compact'),
    ('groq', 'meta-llama/llama-prompt-guard-2-22m', 'Llama Prompt Guard 2 22M', 'Meta''s prompt-injection classifier. Special-purpose, not for general chat.', 512, '22M', 'Dense Transformer', '["text"]', '["text"]', '["safety", "classifier", "special-purpose"]', '{"function_calling": false, "structured_output": false, "reasoning": false, "thinking": false}', 'fast', '["prompt safety", "classification"]', '{"input": 0.0, "output": 0.0}', 0, '', 'compact'),
    ('groq', 'meta-llama/llama-prompt-guard-2-86m', 'Prompt Guard 2 86M', 'Meta''s larger prompt-injection classifier. Special-purpose, not for general chat.', 512, '86M', 'Dense Transformer', '["text"]', '["text"]', '["safety", "classifier", "special-purpose"]', '{"function_calling": false, "structured_output": true, "reasoning": false, "thinking": false}', 'fast', '["prompt safety", "classification"]', '{"input": 0.0, "output": 0.0}', 0, '', 'compact')
ON CONFLICT(provider_id, id) DO UPDATE SET
    name = excluded.name,
    description = excluded.description,
    context_window = excluded.context_window,
    parameters = excluded.parameters,
    architecture = excluded.architecture,
    input_modalities = excluded.input_modalities,
    output_modalities = excluded.output_modalities,
    tags = excluded.tags,
    model_capabilities_json = excluded.model_capabilities_json,
    speed_tier = excluded.speed_tier,
    best_for = excluded.best_for,
    pricing_json = excluded.pricing_json,
    is_default = excluded.is_default,
    tokenizer = excluded.tokenizer,
    prompt_tier = excluded.prompt_tier
;
