"""
Tests for NotificationPolicy - which job outcomes a notification config sends
"""

import pytest

from borgitory.services.notifications.types import (
    NotificationPolicy,
    NotificationType,
)


@pytest.mark.parametrize(
    "policy, notification_type, expected",
    [
        (NotificationPolicy.ALL, NotificationType.SUCCESS, True),
        (NotificationPolicy.ALL, NotificationType.INFO, True),
        (NotificationPolicy.ALL, NotificationType.WARNING, True),
        (NotificationPolicy.ALL, NotificationType.ERROR, True),
        (NotificationPolicy.ALL, NotificationType.FAILURE, True),
        (NotificationPolicy.WARNINGS_AND_FAILURES, NotificationType.SUCCESS, False),
        (NotificationPolicy.WARNINGS_AND_FAILURES, NotificationType.INFO, False),
        (NotificationPolicy.WARNINGS_AND_FAILURES, NotificationType.WARNING, True),
        (NotificationPolicy.WARNINGS_AND_FAILURES, NotificationType.ERROR, True),
        (NotificationPolicy.WARNINGS_AND_FAILURES, NotificationType.FAILURE, True),
        (NotificationPolicy.FAILURES_ONLY, NotificationType.SUCCESS, False),
        (NotificationPolicy.FAILURES_ONLY, NotificationType.INFO, False),
        (NotificationPolicy.FAILURES_ONLY, NotificationType.WARNING, False),
        (NotificationPolicy.FAILURES_ONLY, NotificationType.ERROR, True),
        (NotificationPolicy.FAILURES_ONLY, NotificationType.FAILURE, True),
    ],
)
def test_allows(
    policy: NotificationPolicy, notification_type: NotificationType, expected: bool
) -> None:
    assert policy.allows(notification_type) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("all", NotificationPolicy.ALL),
        ("warnings_and_failures", NotificationPolicy.WARNINGS_AND_FAILURES),
        ("failures_only", NotificationPolicy.FAILURES_ONLY),
        (None, NotificationPolicy.ALL),
        ("", NotificationPolicy.ALL),
        ("bogus", NotificationPolicy.ALL),
    ],
)
def test_from_value(value: str, expected: NotificationPolicy) -> None:
    assert NotificationPolicy.from_value(value) == expected


def test_every_policy_has_a_label() -> None:
    for policy in NotificationPolicy:
        assert policy.label
