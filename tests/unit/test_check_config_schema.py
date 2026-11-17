"""
Validation of repository check policy fields: frequency and archive filters
"""

import pytest
from pydantic import ValidationError

from borgitory.models.schemas import (
    CheckRequest,
    RepositoryCheckConfigCreate,
    RepositoryCheckConfigUpdate,
)


class TestCheckConfigFrequency:
    @pytest.mark.parametrize("value", [None, "", "  "])
    def test_blank_means_every_run(self, value: object) -> None:
        config = RepositoryCheckConfigCreate(name="policy", frequency_days=value)  # type: ignore[arg-type]

        assert config.frequency_days is None

    @pytest.mark.parametrize("value, expected", [(14, 14), ("14", 14), ("365", 365)])
    def test_accepts_days(self, value: object, expected: int) -> None:
        config = RepositoryCheckConfigCreate(name="policy", frequency_days=value)  # type: ignore[arg-type]

        assert config.frequency_days == expected

    @pytest.mark.parametrize("value", [0, -1, 366, "abc"])
    def test_rejects_out_of_range(self, value: object) -> None:
        with pytest.raises(ValidationError):
            RepositoryCheckConfigCreate(name="policy", frequency_days=value)  # type: ignore[arg-type]

    def test_update_can_clear_frequency(self) -> None:
        update = RepositoryCheckConfigUpdate(frequency_days="")  # type: ignore[arg-type]

        assert update.model_dump(exclude_unset=True) == {"frequency_days": None}

    def test_update_without_frequency_leaves_it_alone(self) -> None:
        update = RepositoryCheckConfigUpdate(name="renamed")

        assert "frequency_days" not in update.model_dump(exclude_unset=True)

    @pytest.mark.parametrize("value", [0, 366])
    def test_update_rejects_out_of_range(self, value: int) -> None:
        with pytest.raises(ValidationError):
            RepositoryCheckConfigUpdate(frequency_days=value)


class TestArchiveFilterCharacters:
    """Archive filters that create_borg_command would reject are refused when saved,
    instead of failing the check when it runs"""

    @pytest.mark.parametrize("field", ["archive_prefix", "archive_glob"])
    @pytest.mark.parametrize("value", ["R&D-*", "a;b", "a|b", "a$b", "a`b", "a>b"])
    def test_policy_rejects_unsupported_characters(
        self, field: str, value: str
    ) -> None:
        with pytest.raises(ValidationError, match="Archive filters cannot contain"):
            RepositoryCheckConfigCreate.model_validate({"name": "p", field: value})
        with pytest.raises(ValidationError, match="Archive filters cannot contain"):
            RepositoryCheckConfigUpdate.model_validate({field: value})

    @pytest.mark.parametrize("field", ["archive_prefix", "archive_glob"])
    def test_custom_check_rejects_unsupported_characters(self, field: str) -> None:
        with pytest.raises(ValidationError, match="Archive filters cannot contain"):
            CheckRequest.model_validate({"repository_id": 1, field: "R&D-*"})

    @pytest.mark.parametrize("value", ["host-*", "backup-2024-??-*", "[ab]*", ""])
    def test_accepts_glob_patterns(self, value: str) -> None:
        config = RepositoryCheckConfigCreate.model_validate(
            {"name": "p", "archive_glob": value}
        )

        assert config.archive_glob == value
