"""Tests for cron expression APScheduler compatibility helpers."""

import pytest
from apscheduler.triggers.cron import CronTrigger

from borgitory.services.scheduling.cron_utils import normalize_cron_for_apscheduler


class TestNormalizeCronForAPScheduler:
    def test_sunday_zero_maps_to_sun(self) -> None:
        assert normalize_cron_for_apscheduler("0 1 * * 0") == "0 1 * * sun"

    def test_sunday_seven_maps_to_sun(self) -> None:
        assert normalize_cron_for_apscheduler("0 1 * * 7") == "0 1 * * sun"

    def test_saturday_maps_to_sat(self) -> None:
        assert normalize_cron_for_apscheduler("0 1 * * 6") == "0 1 * * sat"

    def test_weekday_range_maps_to_names(self) -> None:
        assert (
            normalize_cron_for_apscheduler("0 9 * * 1-5")
            == "0 9 * * mon,tue,wed,thu,fri"
        )

    def test_all_days_range_expands_to_names(self) -> None:
        assert (
            normalize_cron_for_apscheduler("0 1 * * 0-6")
            == "0 1 * * sun,mon,tue,wed,thu,fri,sat"
        )

    def test_zero_through_seven_dedupes_sunday(self) -> None:
        assert (
            normalize_cron_for_apscheduler("0 1 * * 0-7")
            == "0 1 * * sun,mon,tue,wed,thu,fri,sat"
        )

    def test_list_of_days(self) -> None:
        assert normalize_cron_for_apscheduler("0 1 * * 0,6") == "0 1 * * sun,sat"

    def test_star_unchanged(self) -> None:
        assert normalize_cron_for_apscheduler("0 2 * * *") == "0 2 * * *"

    def test_named_days_passthrough_lowercased(self) -> None:
        assert normalize_cron_for_apscheduler("0 1 * * SUN") == "0 1 * * sun"
        assert normalize_cron_for_apscheduler("0 1 * * Mon-Fri") == "0 1 * * mon-fri"

    def test_star_step_unchanged(self) -> None:
        assert normalize_cron_for_apscheduler("0 1 * * */2") == "0 1 * * */2"

    def test_whitespace_stripped(self) -> None:
        assert normalize_cron_for_apscheduler("  0 1 * * 7  ") == "0 1 * * sun"

    def test_invalid_day_raises(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            normalize_cron_for_apscheduler("0 1 * * 8")

    def test_non_five_field_expression_returned_stripped(self) -> None:
        assert normalize_cron_for_apscheduler("  0 1 * *  ") == "0 1 * *"


class TestNormalizedCronAcceptedByAPScheduler:
    @pytest.mark.parametrize(
        "expr",
        [
            "0 1 * * 0",
            "0 1 * * 7",
            "0 1 * * sun",
            "0 9 * * 1-5",
            "0 1 * * 0,6",
            "0 2 * * *",
        ],
    )
    def test_normalized_expression_builds_trigger(self, expr: str) -> None:
        normalized = normalize_cron_for_apscheduler(expr)
        trigger = CronTrigger.from_crontab(normalized)
        assert trigger is not None
