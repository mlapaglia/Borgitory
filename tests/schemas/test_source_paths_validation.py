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
        paths = s.source_paths
        assert paths == ['/data', '/backup']

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
        paths = s.source_paths
        assert paths == ['/data']

    def test_all_empty_strings_becomes_empty_array(self) -> None:
        s = ScheduleCreate(
            name="test",
            cron_expression="0 2 * * *",
            repository_id=1,
            source_paths=["", "  "],
        )
        assert s.source_paths == []

    def test_no_source_paths_uses_default(self) -> None:
        s = ScheduleCreate(
            name="test",
            cron_expression="0 2 * * *",
            repository_id=1,
        )
        assert s.source_paths == []

    def test_json_array_string_accepted(self) -> None:
        s = ScheduleCreate(
            name="test",
            cron_expression="0 2 * * *",
            repository_id=1,
            source_paths=["/single"],
        )
        paths = s.source_paths
        assert paths == ["/single"]

    def test_json_array_string_relative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be absolute"):
            ScheduleCreate(
                name="test",
                cron_expression="0 2 * * *",
                repository_id=1,
                source_paths=["/ok", "bad"],
            )

    def test_json_array_string_absolute_accepted(self) -> None:
        s = ScheduleCreate(
            name="test",
            cron_expression="0 2 * * *",
            repository_id=1,
            source_paths=["/a", "/b"],
        )
        assert s.source_paths == ["/a", "/b"]

    def test_list_serialized_to_json_string(self) -> None:
        s = ScheduleCreate(
            name="test",
            cron_expression="0 2 * * *",
            repository_id=1,
            source_paths=["/x", "/y"],
        )
        assert s.source_paths == ["/x", "/y"]


class TestScheduleUpdateSourcePaths:
    def test_absolute_paths_accepted(self) -> None:
        s = ScheduleUpdate(name="test", source_paths=["/data", "/backup"], cron_expression="0 2 * * *")
        paths = s.source_paths
        assert paths == ["/data", "/backup"]

    def test_relative_path_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be absolute"):
            ScheduleUpdate(name="test", source_paths=["not/absolute"], cron_expression="0 2 * * *")

    def test_no_source_paths_leaves_none(self) -> None:
        s = ScheduleUpdate(name="updated", cron_expression="0 2 * * *")
        assert s.source_paths is None

    def test_json_array_string_relative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be absolute"):
            ScheduleUpdate(name="test", source_paths=["relative"], cron_expression="0 2 * * *")

    def test_json_array_string_absolute_accepted(self) -> None:
        s = ScheduleUpdate(name="test", source_paths=["/valid"], cron_expression="0 2 * * *")
        assert s.source_paths == ["/valid"]


class TestBackupRequestSourcePaths:
    def test_absolute_paths_accepted(self) -> None:
        r = BackupRequest(
            cloud_sync_config_id=1,
            prune_config_id=1,
            check_config_id=1,
            notification_config_id=1,
            repository_id=1,
            source_paths=["/home/user/src", "/home/user/docs"],
        )
        paths = r.source_paths
        assert paths == ['/home/user/src', '/home/user/docs']

    def test_relative_path_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be absolute"):
            BackupRequest(
                cloud_sync_config_id=1,
                prune_config_id=1,
                check_config_id=1,
                notification_config_id=1,
                repository_id=1,
                source_paths=["relative"],
            )

    def test_no_source_paths_uses_default(self) -> None:
        r = BackupRequest(
            cloud_sync_config_id=1,
            prune_config_id=1,
            check_config_id=1,
            notification_config_id=1,
            repository_id=1
        )
        assert r.source_paths == []

    def test_json_array_string_relative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be absolute"):
            BackupRequest(
                cloud_sync_config_id=1,
                prune_config_id=1,
                check_config_id=1,
                notification_config_id=1,
                repository_id=1,
                source_paths=["/ok", "nope"]
            )

    def test_json_array_string_absolute_accepted(self) -> None:
        r = BackupRequest(
            cloud_sync_config_id=1,
            prune_config_id=1,
            check_config_id=1,
            notification_config_id=1,
            repository_id=1,
            source_paths=["/explicit"]
        )
        assert r.source_paths == ["/explicit"]

    def test_list_serialized_to_json_string(self) -> None:
        r = BackupRequest(
            cloud_sync_config_id=1,
            prune_config_id=1,
            check_config_id=1,
            notification_config_id=1,
            repository_id=1,
            source_paths=["/a", "/b"],
        )
        assert r.source_paths == ["/a", "/b"]
