import pytest
from pydantic import ValidationError

from manta.routes.v1.requests.playbook_request import ValidatePlaybookConfigRequest


def test_validate_playbook_config_request_leaves_the_config_out_when_none_is_given() -> None:
    # When
    request = ValidatePlaybookConfigRequest()

    # Then the service falls back to the playbook's own default_config
    assert request.config is None


def test_validate_playbook_config_request_rejects_a_config_that_is_not_a_mapping() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        ValidatePlaybookConfigRequest(config=["not", "a", "mapping"])
