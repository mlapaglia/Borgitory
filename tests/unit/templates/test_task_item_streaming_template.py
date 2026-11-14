"""
Regression tests for the streaming task item template (issue #262).

htmx inherits ``hx-target`` / ``hx-swap`` from ancestor elements, and the SSE
extension uses them when applying ``sse-swap`` events. The task header carries
``hx-target="#task-item-..."`` and ``hx-swap="outerHTML"`` for the expand/collapse
toggle, so any ``sse-swap`` element nested inside it that doesn't set its own
target replaces the whole task item with the event payload. In practice the
task item turned into a bare "Running" badge when a task started.
"""

from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Environment, FileSystemLoader

from borgitory.dependencies import datetime_browser_filter
from borgitory.services.jobs.job_models import TaskStatusEnum

VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}


class _SseSwapCollector(HTMLParser):
    """Collect each sse-swap element with its attributes and its ancestors' attributes."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[dict[str, str | None]] = []
        self.sse_elements: list[
            tuple[dict[str, str | None], list[dict[str, str | None]]]
        ] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if "sse-swap" in attr_map:
            self.sse_elements.append((attr_map, list(self.stack)))
        if tag not in VOID_TAGS:
            self.stack.append(attr_map)

    def handle_endtag(self, tag: str) -> None:
        if tag not in VOID_TAGS and self.stack:
            self.stack.pop()


@pytest.fixture
def jinja_env() -> Environment:
    template_dir = (
        Path(__file__).parent.parent.parent.parent / "src" / "borgitory" / "templates"
    )
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    env.filters["format_datetime_browser"] = datetime_browser_filter
    env.globals["TaskStatusEnum"] = TaskStatusEnum
    return env


def _render(env: Environment, status: TaskStatusEnum, expanded: bool) -> str:
    task = SimpleNamespace(
        task_order=1,
        task_name="Backup Immich",
        status=status,
        started_at=datetime(2026, 10, 18, 12, 28, 12),
        completed_at=None,
        output="",
        error=None,
    )
    job = SimpleNamespace(id="85ae83bc-05ed-45f0-967b-b69c4e79982d")
    return env.get_template("partials/jobs/task_item_streaming.html").render(
        job=job, task=task, task_expanded=expanded, browser_tz_offset=None
    )


@pytest.mark.parametrize("status", [TaskStatusEnum.PENDING, TaskStatusEnum.RUNNING])
@pytest.mark.parametrize("expanded", [False, True])
def test_sse_swap_elements_do_not_inherit_task_item_target(
    jinja_env: Environment, status: TaskStatusEnum, expanded: bool
) -> None:
    parser = _SseSwapCollector()
    parser.feed(_render(jinja_env, status, expanded))

    assert parser.sse_elements, "expected sse-swap elements in the task item"
    for attrs, ancestors in parser.sse_elements:
        inherited_target = any("hx-target" in a for a in ancestors)
        if inherited_target:
            assert "hx-target" in attrs, (
                f"sse-swap={attrs['sse-swap']!r} would inherit an ancestor hx-target "
                "and replace the wrong element"
            )


def test_status_badge_wrapper_swaps_inner_html_on_itself(
    jinja_env: Environment,
) -> None:
    parser = _SseSwapCollector()
    parser.feed(_render(jinja_env, TaskStatusEnum.PENDING, expanded=False))

    badge = next(a for a, _ in parser.sse_elements if a["sse-swap"] == "task-1-status")
    assert badge["id"] == "task-status-badge-85ae83bc-05ed-45f0-967b-b69c4e79982d-1"
    assert badge["hx-target"] == "this"
    # innerHTML keeps the wrapper (and its sse-swap listener) in place so later
    # status events (e.g. Running -> Completed) still apply.
    assert badge["hx-swap"] == "innerHTML"
