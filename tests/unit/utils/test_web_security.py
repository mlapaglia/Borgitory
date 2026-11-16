from typing import Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from borgitory.utils.web_security import (
    CrossSiteRequestMiddleware,
    LoginThrottle,
    hash_session_token,
    safe_redirect_target,
)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.add_middleware(
        CrossSiteRequestMiddleware, trusted_origins=["https://proxy.example"]
    )

    @app.post("/action")
    async def action() -> Dict[str, bool]:
        return {"ok": True}

    @app.get("/read")
    async def read() -> Dict[str, bool]:
        return {"ok": True}

    return TestClient(app, base_url="http://borg.local:8000")


class TestCrossSiteRequestMiddleware:
    @pytest.mark.parametrize("site", ["cross-site", "same-site"])
    def test_rejects_cross_origin_fetch(self, client: TestClient, site: str) -> None:
        resp = client.post("/action", headers={"Sec-Fetch-Site": site})
        assert resp.status_code == 403

    @pytest.mark.parametrize("site", ["same-origin", "none"])
    def test_allows_same_origin_fetch(self, client: TestClient, site: str) -> None:
        resp = client.post("/action", headers={"Sec-Fetch-Site": site})
        assert resp.status_code == 200

    def test_safe_methods_never_blocked(self, client: TestClient) -> None:
        resp = client.get("/read", headers={"Sec-Fetch-Site": "cross-site"})
        assert resp.status_code == 200

    def test_origin_fallback_rejects_foreign_origin(self, client: TestClient) -> None:
        resp = client.post("/action", headers={"Origin": "http://evil.local:8000"})
        assert resp.status_code == 403

    def test_origin_fallback_rejects_other_port(self, client: TestClient) -> None:
        resp = client.post("/action", headers={"Origin": "http://borg.local:9000"})
        assert resp.status_code == 403

    def test_origin_fallback_allows_matching_host(self, client: TestClient) -> None:
        resp = client.post("/action", headers={"Origin": "http://borg.local:8000"})
        assert resp.status_code == 200

    def test_null_origin_rejected(self, client: TestClient) -> None:
        resp = client.post("/action", headers={"Origin": "null"})
        assert resp.status_code == 403

    def test_trusted_origin_allowed(self, client: TestClient) -> None:
        resp = client.post(
            "/action",
            headers={"Origin": "https://proxy.example", "Sec-Fetch-Site": "cross-site"},
        )
        assert resp.status_code == 200

    def test_non_browser_client_allowed(self, client: TestClient) -> None:
        assert client.post("/action").status_code == 200


class TestLoginThrottle:
    def test_blocks_after_max_failures(self) -> None:
        throttle = LoginThrottle(max_failures=3, window_seconds=60)
        for _ in range(2):
            throttle.record_failure("1.2.3.4")
        assert throttle.retry_after("1.2.3.4") is None
        throttle.record_failure("1.2.3.4")
        assert throttle.retry_after("1.2.3.4") is not None
        assert throttle.retry_after("5.6.7.8") is None

    def test_reset_clears_failures(self) -> None:
        throttle = LoginThrottle(max_failures=1, window_seconds=60)
        throttle.record_failure("k")
        throttle.reset("k")
        assert throttle.retry_after("k") is None

    def test_failures_expire(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import borgitory.utils.web_security as ws

        now = [1000.0]
        monkeypatch.setattr(ws.time, "monotonic", lambda: now[0])
        throttle = LoginThrottle(max_failures=1, window_seconds=60)
        throttle.record_failure("k")
        assert throttle.retry_after("k") is not None
        now[0] += 61
        assert throttle.retry_after("k") is None

    def test_tracked_clients_bounded(self) -> None:
        throttle = LoginThrottle(max_failures=5, max_tracked_clients=3)
        for i in range(10):
            throttle.record_failure(f"client-{i}")
        assert len(throttle._failures) == 3


@pytest.mark.parametrize(
    "target,expected",
    [
        ("/schedules", "/schedules"),
        ("/archives?repo=1", "/archives?repo=1"),
        (None, "/repositories"),
        ("", "/repositories"),
        ("https://evil.example", "/repositories"),
        ("//evil.example", "/repositories"),
        ("/\\evil.example", "/evil.example"),  # backslash stripped -> local path
        ("javascript:alert(1)", "/repositories"),
        ("relative", "/repositories"),
    ],
)
def test_safe_redirect_target(target: str, expected: str) -> None:
    assert safe_redirect_target(target) == expected


def test_hash_session_token_is_stable_and_not_identity() -> None:
    assert hash_session_token("abc") == hash_session_token("abc")
    assert hash_session_token("abc") != "abc"
    assert len(hash_session_token("abc")) == 64
