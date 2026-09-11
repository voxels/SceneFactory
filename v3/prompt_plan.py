"""Strict prompt-planner contract shared by compilation and generation adapters."""

from __future__ import annotations


def build_contract(production_constraints: dict | None) -> dict:
    constraints = production_constraints or {}
    issue_codes = list(dict.fromkeys(constraints.get("issue_codes") or []))
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["positive_prompt", "negative_prompt", "issue_codes"],
        "properties": {
            "positive_prompt": {"type": "string", "minLength": 1},
            "negative_prompt": {"type": "string"},
            "issue_codes": {
                "type": "array",
                "uniqueItems": True,
                "items": {"type": "string", "enum": issue_codes},
            },
        },
    }
    return {
        "provider": "qwen_openai_compatible",
        "system_prompt": (
            "Return only one JSON object matching the supplied schema. "
            "Do not invent issue codes. The only allowed issue codes are: "
            + ", ".join(issue_codes)
            + ". Enforce every production constraint before emitting a prompt."
        ),
        "production_constraints": list(constraints.get("required") or []),
        "issue_codes": issue_codes,
        "response_schema": schema,
    }


def validate_contract(contract: dict) -> None:
    issue_codes = contract.get("issue_codes") or []
    schema_codes = (
        contract.get("response_schema", {})
        .get("properties", {})
        .get("issue_codes", {})
        .get("items", {})
        .get("enum")
    )
    if schema_codes != issue_codes:
        raise ValueError("Prompt-planner schema issue codes do not match project production_constraints")
    system_prompt = contract.get("system_prompt", "")
    missing = [code for code in issue_codes if code not in system_prompt]
    if missing:
        raise ValueError(f"Prompt-planner system prompt is missing issue codes: {', '.join(missing)}")


def validate_response(contract: dict, response: dict) -> dict:
    validate_contract(contract)
    if set(response) != {"positive_prompt", "negative_prompt", "issue_codes"}:
        raise ValueError("Prompt plan must contain only positive_prompt, negative_prompt, and issue_codes")
    if not isinstance(response["positive_prompt"], str) or not response["positive_prompt"].strip():
        raise ValueError("Prompt plan positive_prompt must be a non-empty string")
    if not isinstance(response["negative_prompt"], str):
        raise ValueError("Prompt plan negative_prompt must be a string")
    if not isinstance(response["issue_codes"], list):
        raise ValueError("Prompt plan issue_codes must be an array")
    unknown = sorted(set(response["issue_codes"]) - set(contract["issue_codes"]))
    if unknown:
        raise ValueError(f"Prompt plan contains unknown issue codes: {', '.join(unknown)}")
    return response
