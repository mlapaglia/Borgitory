"""
Tests for NotificationTaskExecutor honoring the notification config's notify_on policy
"""

import uuid
from typing import List
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from borgitory.models.database import NotificationConfig
from borgitory.models.job_results import JobStatusEnum, JobTypeEnum
from borgitory.services.jobs.job_models import (
    BorgJob,
    BorgJobTask,
    TaskStatusEnum,
    TaskTypeEnum,
)
from borgitory.services.jobs.task_executors.notification_task_executor import (
    NotificationTaskExecutor,
)
from borgitory.services.notifications.apprise_storage import StoredAppriseConfig
from borgitory.services.notifications.types import (
    NotificationPolicy,
    NotificationResult,
    NotificationType,
)
from borgitory.utils.datetime_utils import now_utc
from tests.fixtures.notification_fixtures import create_notification_config


@pytest.fixture
def notification_service() -> Mock:
    service = Mock()
    service.load_config_from_storage.return_value = StoredAppriseConfig(
        mode="service", service="discord", service_name="Discord"
    )
    service.send_notification = AsyncMock(
        return_value=NotificationResult(success=True, message="sent")
    )
    return service


@pytest.fixture
def executor(
    test_db: AsyncSession, notification_service: Mock
) -> NotificationTaskExecutor:
    session_maker = async_sessionmaker(
        test_db.bind, class_=AsyncSession, expire_on_commit=False
    )
    return NotificationTaskExecutor(
        job_executor=Mock(),
        output_manager=Mock(),
        event_broadcaster=Mock(),
        session_maker=session_maker,
        notification_service=notification_service,
    )


async def _add_config(test_db: AsyncSession, policy: NotificationPolicy) -> int:
    config: NotificationConfig = create_notification_config(f"policy-{policy.value}")
    config.notify_on = policy.value
    test_db.add(config)
    await test_db.commit()
    await test_db.refresh(config)
    return config.id


def _job(outcome: NotificationType, config_id: int) -> tuple[BorgJob, BorgJobTask]:
    tasks: List[BorgJobTask] = []
    if outcome == NotificationType.ERROR:
        tasks.append(
            BorgJobTask(
                task_type=TaskTypeEnum.BACKUP,
                task_name="Backup",
                status=TaskStatusEnum.FAILED,
            )
        )
    else:
        tasks.append(
            BorgJobTask(
                task_type=TaskTypeEnum.BACKUP,
                task_name="Backup",
                status=TaskStatusEnum.COMPLETED,
            )
        )
        tasks.append(
            BorgJobTask(
                task_type=TaskTypeEnum.PRUNE,
                task_name="Prune",
                status=TaskStatusEnum.FAILED
                if outcome == NotificationType.WARNING
                else TaskStatusEnum.COMPLETED,
            )
        )

    notification_task = BorgJobTask(
        task_type=TaskTypeEnum.NOTIFICATION,
        task_name="Notify",
        status=TaskStatusEnum.RUNNING,
        parameters={"config_id": config_id},
    )
    tasks.append(notification_task)

    job = BorgJob(
        id=uuid.uuid4(),
        job_type=JobTypeEnum.COMPOSITE,
        status=JobStatusEnum.RUNNING,
        started_at=now_utc(),
        tasks=tasks,
    )
    return job, notification_task


@pytest.mark.parametrize(
    "policy, outcome, should_send",
    [
        (NotificationPolicy.ALL, NotificationType.SUCCESS, True),
        (NotificationPolicy.ALL, NotificationType.WARNING, True),
        (NotificationPolicy.ALL, NotificationType.ERROR, True),
        (NotificationPolicy.WARNINGS_AND_FAILURES, NotificationType.SUCCESS, False),
        (NotificationPolicy.WARNINGS_AND_FAILURES, NotificationType.WARNING, True),
        (NotificationPolicy.WARNINGS_AND_FAILURES, NotificationType.ERROR, True),
        (NotificationPolicy.FAILURES_ONLY, NotificationType.SUCCESS, False),
        (NotificationPolicy.FAILURES_ONLY, NotificationType.WARNING, False),
        (NotificationPolicy.FAILURES_ONLY, NotificationType.ERROR, True),
    ],
)
async def test_policy_filters_notifications(
    executor: NotificationTaskExecutor,
    notification_service: Mock,
    test_db: AsyncSession,
    policy: NotificationPolicy,
    outcome: NotificationType,
    should_send: bool,
) -> None:
    config_id = await _add_config(test_db, policy)
    job, task = _job(outcome, config_id)

    result = await executor.execute_notification_task(job, task, len(job.tasks) - 1)

    assert result is True
    if should_send:
        notification_service.send_notification.assert_awaited_once()
        sent = notification_service.send_notification.await_args.args[1]
        assert sent.notification_type == outcome
        assert task.status == TaskStatusEnum.COMPLETED
    else:
        notification_service.send_notification.assert_not_awaited()
        assert task.status == TaskStatusEnum.SKIPPED
        assert task.return_code == 0
        assert any(
            "filtered by policy" in str(line) and policy.label in str(line)
            for line in task.output_lines
        )
