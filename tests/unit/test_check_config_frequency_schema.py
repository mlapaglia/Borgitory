"""
Validation of the frequency_days field on repository check policies
"""

import pytest
from pydantic import ValidationError

from borgitory.models.schemas import (
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
