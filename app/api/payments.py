from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.booking import Booking
from app.models.user import User
from app.schemas.payment import PaymentIntentResponse
from app.services.payments import (
    PaymentError,
    RealStripeGateway,
    StripeGateway,
    create_payment_for_booking,
)

router = APIRouter(prefix="/bookings", tags=["payments"])


def _gateway() -> StripeGateway:
    return RealStripeGateway()


@router.post(
    "/{booking_id}/payments",
    response_model=PaymentIntentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_payment(
    booking_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    gateway: StripeGateway = Depends(_gateway),
) -> PaymentIntentResponse:
    booking = await db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="booking not found")
    if booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="not your booking")

    try:
        payment, client_secret = await create_payment_for_booking(db, booking, gateway)
    except PaymentError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(payment)
    return PaymentIntentResponse(
        payment_id=payment.id,
        client_secret=client_secret,
        amount_cents=payment.amount_cents,
        status=payment.status,
    )
