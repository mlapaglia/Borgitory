"""Tests for source_paths validation in Pydantic schemas."""

import json
import pytest
from pydantic import ValidationError

from borgitory.models.schemas import (
    ScheduleCreate,
    ScheduleUpdate,
    BackupRequest,
)


class TestScheduleCreateSourcePaths:
    def test_absolute_paths_accepted(self) -> None:
        s = ScheduleCreate(
            name="test",
            cron_expression="0 2 * * *",
            repository_id=1,
            source_paths=["/data", "/backup"],
        )
        paths = json.loads(s.source_path)  # type: ignore[arg-type]
        assert paths == ["/data", "/backup"]

    def test_relative_path_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be absolute"):
            ScheduleCreate(
                name="test",
                cron_expression="0 2 * * *",
                repository_id=1,
                source_paths=["relative/path"],
            )

    def test_mixed_absolute_and_relative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Invalid: data"):
            ScheduleCreate(
                name="test",
                cron_expression="0 2 * * *",
                repository_id=1,
                source_paths=["/valid", "data"],
            )

    def test_empty_strings_filtered_before_validation(self) -> None:
        s = ScheduleCreate(
            name="test",
            cron_expression="0 2 * * *",
            repository_id=1,
            source_paths=["/data", "", "  "],
        )
        paths = json.loads(s.source_path)  # type: ignore[arg-type]
        assert paths == ["/data"]

    def test_all_empty_strings_falls_through_to_default(self) -> None:
        s = ScheduleCreate(
            name="test",
            cron_expression="0 2 * * *",
            repository_id=1,
            source_paths=["", "  "],
        )
        assert s.source_path == "/data"

    def test_no_source_paths_uses_default(self) -> None:
        s = ScheduleCreate(
            name="test",
            cron_expression="0 2 * * *",
            repository_id=1,
        )
        assert s.source_path == "/data"

    def test_bare_string_source_paths(self) -> None:
        s = ScheduleCreate(
            name="test",
            cron_expression="0 2 * * *",
            repository_id=1,
            source_paths="/single",
        )
        paths = json.loads(s.source_path)  # type: ignore[arg-type]
        assert paths == ["/single"]

    def test_bare_string_relative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be absolute"):
            ScheduleCreate(
                name="test",
                cron_expression="0 2 * * *",
                repository_id=1,
                source_paths="no-slash",
            )

    def test_direct_source_path_absolute_accepted(self) -> None:
        s = ScheduleCreate(
            name="test",
            cron_expression="0 2 * * *",
            repository_id=1,
            source_path="/direct",
        )
        assert s.source_path == "/direct"

    def test_direct_source_path_relative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be absolute"):
            ScheduleCreate(
                name="test",
                cron_expression="0 2 * * *",
                repository_id=1,
                source_path="relative",
            )

    def test_direct_source_path_json_array_relative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be absolute"):
            ScheduleCreate(
                name="test",
                cron_expression="0 2 * * *",
                repository_id=1,
                source_path='["/ok", "bad"]',
            )

    def test_direct_source_path_json_array_absolute_accepted(self) -> None:
        s = ScheduleCreate(
            name="test",
            cron_expression="0 2 * * *",
            repository_id=1,
            source_path='["/a", "/b"]',
        )
        assert s.source_path == '["/a", "/b"]'


class TestScheduleUpdateSourcePaths:
    def test_absolute_paths_accepted(self) -> None:
        s = ScheduleUpdate(source_paths=["/data", "/backup"])
        paths = json.loads(s.source_path)  # type: ignore[arg-type]
        assert paths == ["/data", "/backup"]

    def test_relative_path_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be absolute"):
            ScheduleUpdate(source_paths=["not/absolute"])

    def test_no_source_paths_leaves_none(self) -> None:
        s = ScheduleUpdate(name="updated")
        assert s.source_path is None

    def test_direct_source_path_relative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be absolute"):
            ScheduleUpdate(source_path="relative")

    def test_direct_source_path_absolute_accepted(self) -> None:
        s = ScheduleUpdate(source_path="/valid")
        assert s.source_path == "/valid"


class TestBackupRequestSourcePaths:
    def test_absolute_paths_accepted(self) -> None:
        r = BackupRequest(
            repository_id=1,
            source_paths=["/home/user/src", "/home/user/docs"],
        )
        paths = json.loads(r.source_path)
        assert paths == ["/home/user/src", "/home/user/docs"]

    def test_relative_path_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be absolute"):
            BackupRequest(
                repository_id=1,
                source_paths=["relative"],
            )

    def test_no_source_paths_uses_default(self) -> None:
        r = BackupRequest(repository_id=1)
        assert r.source_path == "/"

    def test_direct_source_path_relative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be absolute"):
            BackupRequest(repository_id=1, source_path="relative")

    def test_direct_source_path_json_array_relative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be absolute"):
            BackupRequest(repository_id=1, source_path='["/ok", "nope"]')

    def test_direct_source_path_absolute_accepted(self) -> None:
        r = BackupRequest(repository_id=1, source_path="/explicit")
        assert r.source_path == "/explicit"
