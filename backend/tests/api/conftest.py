from collections.abc import Callable, Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.core.config import get_settings

PASSWORD = "mesh-demo-2026"


class Api:
    """A logged-in browser: session cookie plus the CSRF and Idempotency-Key headers."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def login(self, email: str) -> "Api":
        r = self.client.post(
            "/v1/auth/login",
            json={"email": email, "password": PASSWORD},
            headers={"X-Requested-With": "mesh-web"},
        )
        assert r.status_code == 200, r.text
        return self

    def get(self, path: str, **kw):  # type: ignore[no-untyped-def]
        return self.client.get(path, **kw)

    def post(self, path: str, key: str | None = None, **kw):  # type: ignore[no-untyped-def]
        headers = {
            "X-Requested-With": "mesh-web",
            "Idempotency-Key": key or str(uuid4()),
            **kw.pop("headers", {}),
        }
        return self.client.post(path, headers=headers, **kw)

    def put(self, path: str, key: str | None = None, **kw):  # type: ignore[no-untyped-def]
        headers = {"X-Requested-With": "mesh-web", "Idempotency-Key": key or str(uuid4())}
        return self.client.put(path, headers=headers, **kw)

    def patch(self, path: str, **kw):  # type: ignore[no-untyped-def]
        headers = {"X-Requested-With": "mesh-web", "Idempotency-Key": str(uuid4())}
        return self.client.patch(path, headers=headers, **kw)


@pytest.fixture
def make_api(fresh_db: Engine) -> Iterator[Callable[[str | None], Api]]:
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    clients: list[TestClient] = []
    # One logged-in browser per persona and test, like a real user; this also keeps long
    # multi-member flows under the per-IP login rate limit.
    personas: dict[str, Api] = {}

    def factory(email: str | None = None) -> Api:
        if email and email in personas:
            return personas[email]
        client = TestClient(app, base_url="http://localhost:3010")
        clients.append(client)
        api = Api(client)
        if email:
            personas[email] = api.login(email)
        return api

    yield factory
    for c in clients:
        c.close()
