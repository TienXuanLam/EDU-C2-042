import copy

import pytest
import yaml

from src.services.config_validation_service import validate_profile_config


@pytest.fixture
def config() -> dict:
    with open("config/config.yaml", encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def test_shipped_profile_pack_is_valid(config):
    validate_profile_config(config)


def test_invalid_regex_fails_closed(config):
    broken = copy.deepcopy(config)
    broken["exchange_profile"]["resource_id_pattern"] = "["
    with pytest.raises(ValueError, match="valid regex"):
        validate_profile_config(broken)


def test_unknown_accessibility_descriptor_fails_closed(config):
    broken = copy.deepcopy(config)
    broken["accessibility_profile"]["required_descriptors_by_format"]["video"] = ["unknown"]
    with pytest.raises(ValueError, match="unknown descriptor"):
        validate_profile_config(broken)
