from datetime import datetime

from pydantic import BaseModel

from app.models.payment import PaymentStatus


class PaymentIntentResponse(BaseModel):
    payment_id: int
    client_secret: str
    amount_cents: int
    status: PaymentStatus


class PaymentOut(BaseModel):
    id: int
    booking_id: int
    stripe_payment_intent_id: str
    amount_cents: int
    status: PaymentStatus
    created_at: datetime

    model_config = {"from_attributes": True}
