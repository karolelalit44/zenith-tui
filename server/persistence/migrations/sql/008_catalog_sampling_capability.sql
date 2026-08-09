-- 008: model sampling capability flags
--
-- Some models deprecate the temperature/top_p/top_k sampling params and log a
-- litellm warning on every call (see todo/04-prompt-sampling.md). Rather than
-- special-casing any model family in code, each catalog model declares its own
-- capabilities: a model with `"supports_temperature": false` in
-- model_capabilities_json must not receive a temperature param. The runtime
-- reads the flag generically and sends only the params a model supports.
--
-- Idempotent: json_set is a no-op-preserving merge; marking the same models
-- again just overwrites the same key with the same value. Explicit model ids
-- are used so the data is auditable (no name-pattern heuristics in code).

UPDATE catalog_models
SET model_capabilities_json = json_set(model_capabilities_json, '$.supports_temperature', 0)
WHERE provider_id = 'google'
  AND id IN (
    'gemini-3.5-flash-lite',
    'gemini-3.5-flash',
    'gemini-3.1-pro-preview'
  );
