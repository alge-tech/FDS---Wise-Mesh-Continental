from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.schemas import ApiModel
from app.core.security import Principal, current_principal
from app.modules.fx.models import Currency, FxRate

router = APIRouter(prefix="/v1", tags=["reference"])


class CurrencyOut(ApiModel):
    code: str
    exponent: int
    name: str


class CurrencyList(ApiModel):
    items: list[CurrencyOut]


class RateOut(ApiModel):
    base: str
    quote: str
    rate: str  # decimals travel as strings
    source: str
    valid_from: datetime


class RateList(ApiModel):
    items: list[RateOut]


@router.get("/currencies", response_model=CurrencyList)
def list_currencies(session: Session = Depends(get_session)) -> CurrencyList:
    rows = session.scalars(select(Currency).order_by(Currency.code)).all()
    return CurrencyList(items=[CurrencyOut.model_validate(r) for r in rows])


@router.get("/rates", response_model=RateList)
def list_rates(
    _: Principal = Depends(current_principal), session: Session = Depends(get_session)
) -> RateList:
    rows = session.scalars(select(FxRate).order_by(FxRate.base, FxRate.quote)).all()
    return RateList(
        items=[
            RateOut(
                base=r.base,
                quote=r.quote,
                rate=format(r.rate.normalize(), "f"),
                source=r.source,
                valid_from=r.valid_from,
            )
            for r in rows
        ]
    )
