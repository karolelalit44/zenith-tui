from __future__ import annotations

import json
from typing import Any

from server.config.constants import (
    BUILD_MODE,
    CONCURRENCY_GROUP_LSP,
    CONCURRENCY_GROUP_MCP,
    CONCURRENCY_GROUP_READONLY,
    CONCURRENCY_GROUP_SHELL,
    CONCURRENCY_GROUP_SUBAGENT,
    CONCURRENCY_GROUP_WORKSPACE_MUTATION,
    MAX_TOOL_DESCRIPTION_LENGTH,
    MAX_TOOL_NAME_LENGTH,
    PERMISSION_COMMAND,
    PERMISSION_DELETE,
    PERMISSION_INTERACTION,
    PERMISSION_MCP,
    PERMISSION_NETWORK,
    PERMISSION_READ,
    PERMISSION_SUBAGENT,
    PERMISSION_WRITE,
    PLAN_MODE,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    RISK_SAFE,
)
from server.toolkit.catalog import is_known_capability
from server.toolkit.registry import ToolRegistry

_VALID_MODES = (None, BUILD_MODE, PLAN_MODE)
_VALID_RISK_LEVELS = (RISK_SAFE, RISK_LOW, RISK_MEDIUM, RISK_HIGH)
_VALID_PERMISSION_SCOPES = (
    PERMISSION_READ,
    PERMISSION_WRITE,
    PERMISSION_DELETE,
    PERMISSION_COMMAND,
    PERMISSION_NETWORK,
    PERMISSION_MCP,
    PERMISSION_SUBAGENT,
    PERMISSION_INTERACTION,
)
_VALID_CONCURRENCY_GROUPS = (
    CONCURRENCY_GROUP_READONLY,
    CONCURRENCY_GROUP_WORKSPACE_MUTATION,
    CONCURRENCY_GROUP_SHELL,
    CONCURRENCY_GROUP_LSP,
    CONCURRENCY_GROUP_MCP,
    CONCURRENCY_GROUP_SUBAGENT,
)


def _validate_schema(schema: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(schema, dict):
        return ["schema must be a JSON object"]
    if schema.get("type") != "object":
        errors.append("schema 'type' must be 'object'")
    props = schema.get("properties")
    if not isinstance(props, dict):
        errors.append("schema 'properties' must be an object")
    else:
        for prop_name, prop_def in props.items():
            if not isinstance(prop_name, str) or not prop_name:
                errors.append("schema property names must be non-empty strings")
            if not isinstance(prop_def, dict):
                errors.append(f"property '{prop_name}' must be a JSON schema object")
    required = schema.get("required")
    if required is not None:
        if not isinstance(required, list) or not all(isinstance(r, str) for r in required):
            errors.append("schema 'required' must be a list of strings")
        elif isinstance(props, dict):
            missing = [r for r in required if r not in props]
            if missing:
                errors.append(f"schema 'required' references undefined properties: {missing}")
    try:
        json.dumps(schema, separators=(",", ":"))
    except (TypeError, ValueError):
        errors.append("schema is not JSON-serializable")
    return errors


def validate_registry(registry: ToolRegistry) -> list[str]:
    """Validate a registry's canonical metadata and tool contracts at startup.

    Returns a list of human-readable errors; an empty list means the registry is
    valid. Checks bounded descriptions, valid JSON schemas, valid mode
    declarations, and canonical capability/permission/concurrency metadata.
    """
    errors: list[str] = []
    for name in registry.list_tools():
        tool = registry.get(name)
        if tool is None:
            continue
        if not name:
            errors.append("Tool with empty name registered")
        if len(name) > MAX_TOOL_NAME_LENGTH:
            errors.append(f"Tool '{name}': name exceeds {MAX_TOOL_NAME_LENGTH} chars")
        description = tool.description or ""
        if not description:
            errors.append(f"Tool '{name}': description is empty")
        if len(description) > MAX_TOOL_DESCRIPTION_LENGTH:
            errors.append(f"Tool '{name}': description exceeds {MAX_TOOL_DESCRIPTION_LENGTH} chars")
        if tool.requires_mode not in _VALID_MODES:
            errors.append(f"Tool '{name}': invalid mode declaration '{tool.requires_mode}'")
        if not is_known_capability(tool.capability_id):
            errors.append(f"Tool '{name}': unknown capability_id '{tool.capability_id}'")
        if tool.risk_level not in _VALID_RISK_LEVELS:
            errors.append(f"Tool '{name}': invalid risk_level '{tool.risk_level}'")
        if tool.permission_scope not in _VALID_PERMISSION_SCOPES:
            errors.append(f"Tool '{name}': invalid permission_scope '{tool.permission_scope}'")
        if tool.concurrency_group not in _VALID_CONCURRENCY_GROUPS:
            errors.append(f"Tool '{name}': invalid concurrency_group '{tool.concurrency_group}'")
        if not tool.read_only and tool.permission_scope == PERMISSION_READ:
            errors.append(
                f"Tool '{name}': read_only=False but permission_scope='{PERMISSION_READ}'"
            )
        for schema_error in _validate_schema(tool.get_schema()):
            errors.append(f"Tool '{name}': {schema_error}")
    return errors
