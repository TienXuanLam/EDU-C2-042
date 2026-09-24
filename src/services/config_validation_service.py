"""Fail-closed validation for the institution-supplied metadata profile pack."""

from __future__ import annotations

import re
from typing import Any

_VOCAB_KEYS = ("licence", "language", "format", "accessibility_descriptors")


def _non_empty_strings(value: object, path: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{path} must be a non-empty list of non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{path} must not contain duplicates")
    return value


def validate_profile_config(config: dict[str, Any]) -> None:
    """Validate every deterministic rule dependency before graph compilation."""
    exchange = config.get("exchange_profile")
    curriculum = config.get("curriculum_code_list")
    vocabulary = config.get("controlled_vocabulary")
    accessibility = config.get("accessibility_profile")
    if not isinstance(exchange, dict):
        raise ValueError("exchange_profile must be configured")
    if not isinstance(curriculum, dict):
        raise ValueError("curriculum_code_list must be configured")
    if not isinstance(vocabulary, dict):
        raise ValueError("controlled_vocabulary must be configured")
    if not isinstance(accessibility, dict):
        raise ValueError("accessibility_profile must be configured")

    if not isinstance(exchange.get("version"), str) or not exchange["version"].strip():
        raise ValueError("exchange_profile.version must be a non-empty string")
    _non_empty_strings(exchange.get("required_fields"), "exchange_profile.required_fields")
    for key in ("resource_id_pattern", "date_pattern"):
        pattern = exchange.get(key)
        if not isinstance(pattern, str) or not pattern:
            raise ValueError(f"exchange_profile.{key} must be configured")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"exchange_profile.{key} is not a valid regex: {exc}") from exc

    _non_empty_strings(curriculum.get("subject_codes"), "curriculum_code_list.subject_codes")
    _non_empty_strings(curriculum.get("grade_codes"), "curriculum_code_list.grade_codes")
    for key in _VOCAB_KEYS:
        _non_empty_strings(vocabulary.get(key), f"controlled_vocabulary.{key}")

    descriptor_map = accessibility.get("required_descriptors_by_format")
    if not isinstance(descriptor_map, dict):
        raise ValueError("accessibility_profile.required_descriptors_by_format must be a mapping")
    formats = set(vocabulary["format"])
    descriptors = set(vocabulary["accessibility_descriptors"])
    for resource_format, required in descriptor_map.items():
        if resource_format not in formats:
            raise ValueError(f"accessibility profile references unknown format {resource_format!r}")
        required_values = _non_empty_strings(required, f"accessibility descriptor list for {resource_format!r}")
        unknown = set(required_values) - descriptors
        if unknown:
            raise ValueError(f"accessibility profile references unknown descriptor(s): {sorted(unknown)}")

    system_prompt = config.get("system_prompt")
    if system_prompt is not None and not isinstance(system_prompt, str):
        raise ValueError("system_prompt must be a string or null")
