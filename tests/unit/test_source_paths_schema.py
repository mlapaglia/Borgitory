"""
Tests for normalizing source paths on schedule and backup request schemas.
"""

import pytest
from pydantic import ValidationError

from borgitory.models.schemas import (
    BackupRequest,
    ScheduleCreate,
    ScheduleUpdate,
    normalize_source_paths,
)


class TestNormalizeSourcePaths:
    def test_none_is_preserved(self) -> None:
        assert normalize_source_paths(None) is None

    def test_single_string_becomes_list(self) -> None:
        assert normalize_source_paths("/data") == ["/data"]

    def test_blank_string_becomes_empty_list(self) -> None:
        assert normalize_source_paths("   ") == []

    def test_strips_drops_blanks_and_dedupes_in_order(self) -> None:
        assert normalize_source_paths(["", " /b ", "/a", "/b", None]) == ["/b", "/a"]

    def test_relative_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="absolute path"):
            normalize_source_paths(["/data", "data"])

    def test_non_string_entry_rejected(self) -> None:
        with pytest.raises(ValueError):
            normalize_source_paths(["/data", 5])

    def test_non_list_rejected(self) -> None:
        with pytest.raises(ValueError):
            normalize_source_paths(5)


class TestSchemaSourcePaths:
    def test_schedule_create_defaults_to_empty(self) -> None:
        schedule = ScheduleCreate(
            name="s", cron_expression="0 2 * * *", repository_id=1
        )
        assert schedule.source_paths == []

    def test_schedule_create_accepts_string(self) -> None:
        schedule = ScheduleCreate(
            name="s",
            cron_expression="0 2 * * *",
            repository_id=1,
            source_paths="/data",  # type: ignore[arg-type]
        )
        assert schedule.source_paths == ["/data"]

    def test_schedule_update_unset_is_excluded(self) -> None:
        update = ScheduleUpdate(name="s")
        assert "source_paths" not in update.model_dump(exclude_unset=True)

    def test_schedule_update_blank_clears(self) -> None:
        update = ScheduleUpdate(source_paths="")  # type: ignore[arg-type]
        assert update.model_dump(exclude_unset=True) == {"source_paths": []}

    def test_backup_request_multiple_paths(self) -> None:
        request = BackupRequest(repository_id=1, source_paths=["/a", "/b"])
        assert request.source_paths == ["/a", "/b"]

    def test_backup_request_requires_a_path(self) -> None:
        with pytest.raises(ValidationError):
            BackupRequest(repository_id=1, source_paths=[" "])
