from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.payments import _gateway
from app.db.session import get_db
from app.services.payments import StripeGateway, handle_stripe_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    gateway: StripeGateway = Depends(_gateway),
) -> dict[str, str]:
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="missing Stripe-Signature header")

    payload = await request.body()
    try:
        event = gateway.construct_event(payload, stripe_signature)
    except Exception as exc:  # stripe raises SignatureVerificationError
        raise HTTPException(status_code=400, detail=f"invalid signature: {exc}") from exc

    result = await handle_stripe_event(db, event)
    await db.commit()
    return {"result": result}
