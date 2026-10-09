"""Idempotency-Key handling for state-changing POSTs.

The key, a hash of the request and the response are stored in the same transaction as
the change, so a replay returns the stored response and a crash leaves no half state.
A replay with a different body returns 409 IDEMPOTENCY_MISMATCH.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.db import transaction
from app.core.errors import Conflict, ValidationFailed
from app.core.hashing import sha256_hex
from app.core.security import Principal, current_principal


@dataclass(frozen=True)
class Idempotency:
    principal: Principal
    key: str
    method: str
    path: str
    request_hash: str

    def run(self, session: Session, fn: Callable[[Session], Any], status_code: int = 200) -> Any:
        """Run `fn` and store its response in one transaction, or replay a stored one."""
        from app.modules.audit.models import IdempotencyKey

        with transaction(session):
            inserted = session.execute(
                pg_insert(IdempotencyKey)
                .values(
                    user_id=self.principal.user_id,
                    key=self.key,
                    method=self.method,
                    path=self.path,
                    request_hash=self.request_hash,
                    status_code=0,
                    response=None,
                )
                .on_conflict_do_nothing()
                .returning(IdempotencyKey.key)
            ).scalar_one_or_none()
            if inserted is None:
                return self._replay(session)
            payload = jsonable_encoder(fn(session))
            row = session.get(IdempotencyKey, (self.principal.user_id, self.key))
            assert row is not None
            row.status_code = status_code
            row.response = payload
        return JSONResponse(payload, status_code=status_code)

    def run_steps(
        self, session: Session, fn: Callable[[Session], Any], status_code: int = 200
    ) -> Any:
        """For operations that commit several transactions themselves (close, settle).

        A completed key is replayed; otherwise `fn` runs (it must be safe to repeat, which
        the run state machine and settlement jobs guarantee) and the response is stored.
        """
        from app.modules.audit.models import IdempotencyKey

        with transaction(session):
            existing = session.get(IdempotencyKey, (self.principal.user_id, self.key))
            if existing is not None:
                return self._replay(session)
        payload = jsonable_encoder(fn(session))
        with transaction(session):
            session.execute(
                pg_insert(IdempotencyKey)
                .values(
                    user_id=self.principal.user_id,
                    key=self.key,
                    method=self.method,
                    path=self.path,
                    request_hash=self.request_hash,
                    status_code=status_code,
                    response=payload,
                )
                .on_conflict_do_nothing()
            )
        return JSONResponse(payload, status_code=status_code)

    def _replay(self, session: Session) -> JSONResponse:
        from app.modules.audit.models import IdempotencyKey

        row = session.scalars(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == self.principal.user_id, IdempotencyKey.key == self.key
            )
        ).one()
        if row.request_hash != self.request_hash or row.path != self.path:
            raise Conflict(
                "This Idempotency-Key was already used for a different request.",
                code="IDEMPOTENCY_MISMATCH",
            )
        if row.status_code == 0:
            raise Conflict("The original request is still running.", code="IDEMPOTENCY_IN_PROGRESS")
        return JSONResponse(row.response, status_code=row.status_code)


async def idempotency(
    request: Request,
    principal: Principal = Depends(current_principal),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Idempotency:
    if not idempotency_key or len(idempotency_key) > 200:
        raise ValidationFailed(
            "Send an Idempotency-Key header with every change.",
            details={"fields": [{"field": "Idempotency-Key", "reason": "required"}]},
        )
    body = await request.body()
    request_hash = sha256_hex(
        request.method.encode()
        + b"\n"
        + request.url.path.encode()
        + b"\n"
        + request.url.query.encode()
        + b"\n"
        + body
    )
    return Idempotency(principal, idempotency_key, request.method, request.url.path, request_hash)
