import os
import logging
import urllib.parse
import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from ..database import get_db
from .. import models
from ..auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])

PAYPAL_MONTHLY_BUTTON_ID = os.getenv("PAYPAL_MONTHLY_BUTTON_ID", "5UCX7JGEEJ3QJ")
PAYPAL_YEARLY_BUTTON_ID  = os.getenv("PAYPAL_YEARLY_BUTTON_ID",  "F88PZH4KYH6T2")
PAYPAL_IPN_VERIFY_URL    = "https://ipnpb.paypal.com/cgi-bin/webscr"

# Expected subscription amounts — used to verify IPN payment values
_EXPECTED_AMOUNTS = {
    "monthly": 3.99,
    "yearly":  29.99,
}


@router.get("/checkout-url")
def get_checkout_url(
    plan: str = "monthly",
    _current_user: models.User = Depends(get_current_user)
):
    """Return the PayPal hosted-button checkout URL for the chosen plan."""
    button_id = PAYPAL_MONTHLY_BUTTON_ID if plan == "monthly" else PAYPAL_YEARLY_BUTTON_ID
    checkout_url = (
        f"https://www.paypal.com/cgi-bin/webscr"
        f"?cmd=_s-xclick&hosted_button_id={button_id}"
    )
    return {"checkout_url": checkout_url}


@router.post("/webhook")
async def paypal_ipn_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Receive and verify PayPal IPN notifications."""
    raw_body = await request.body()

    verified = await _verify_paypal_ipn(raw_body)
    if not verified:
        logger.warning("PayPal IPN: verification failed — discarding")
        return {"status": "ok"}  # always 200; PayPal retries on non-200

    params   = dict(urllib.parse.parse_qsl(raw_body.decode("utf-8")))
    txn_type = params.get("txn_type", "")
    logger.info(f"PayPal IPN: txn_type={txn_type}")

    if txn_type in ("subscr_signup", "subscr_payment", "subscr_modify"):
        await run_in_threadpool(_handle_subscription_active, params, db)
    elif txn_type in ("subscr_cancel", "subscr_eot"):
        await run_in_threadpool(_handle_subscription_cancelled, params, db)
    elif txn_type == "subscr_failed":
        await run_in_threadpool(_handle_subscription_failed, params, db)

    return {"status": "ok"}


async def _verify_paypal_ipn(raw_body: bytes) -> bool:
    """POST the IPN body back to PayPal for official VERIFIED/INVALID check."""
    try:
        verify_body = b"cmd=_notify-validate&" + raw_body
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                PAYPAL_IPN_VERIFY_URL,
                content=verify_body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        return resp.text.strip() == "VERIFIED"
    except Exception as e:
        logger.error(f"PayPal IPN verification error: {e}")
        return False


def _verify_payment_amount(params: dict, plan: str) -> bool:
    """
    For subscription payment events, verify the charged amount matches expectations.
    Protects against crafted IPNs with $0 or wrong amounts.
    """
    txn_type = params.get("txn_type", "")
    if txn_type != "subscr_payment":
        return True  # Only validate actual payment events, not signups

    currency = params.get("mc_currency", "").upper()
    if currency != "USD":
        logger.warning(f"PayPal IPN: unexpected currency {currency}")
        return False

    try:
        amount = float(params.get("mc_gross", "0"))
    except (ValueError, TypeError):
        logger.warning("PayPal IPN: invalid mc_gross value")
        return False

    if amount <= 0:
        logger.warning(f"PayPal IPN: zero/negative amount {amount}")
        return False

    expected = _EXPECTED_AMOUNTS.get(plan)
    if expected and amount < expected * 0.5:
        # Allow some tolerance for potential discounts/taxes, but block obvious fraud
        logger.warning(f"PayPal IPN: amount {amount} far below expected {expected} for {plan}")
        return False

    return True


def _get_user_from_ipn(params: dict, db: Session):
    """Look up a Zodovia user by their PayPal payer_email."""
    email = params.get("payer_email", "").lower().strip()
    if not email:
        return None
    return db.query(models.User).filter(models.User.email == email).first()


def _handle_subscription_active(params: dict, db: Session):
    subscr_id = params.get("subscr_id", "")
    plan      = params.get("custom", "monthly")   # set in button: custom=monthly / custom=yearly
    txn_type  = params.get("txn_type", "")

    if plan not in ("monthly", "yearly"):
        plan = "monthly"

    # Verify payment amount for actual payment events
    if not _verify_payment_amount(params, plan):
        logger.warning(f"PayPal IPN: amount verification failed for subscr_id={subscr_id}, discarding")
        return

    # For renewals (subscr_payment), look up by stored subscr_id first — more reliable
    # than payer_email because email can differ between PayPal account and Zodovia account.
    user = None
    if txn_type == "subscr_payment" and subscr_id:
        user = db.query(models.User).filter(
            models.User.paypal_subscription_id == subscr_id
        ).first()
    if not user:
        user = _get_user_from_ipn(params, db)
    if not user:
        logger.warning(f"PayPal IPN: no user found for subscr_id={subscr_id}")
        return

    user.is_paid                  = True
    user.paypal_subscription_id   = subscr_id
    user.subscription_status      = "active"
    user.subscription_plan        = plan
    # Reset trial counter so paid users start fresh
    user.trial_uses               = 0
    db.commit()
    logger.info(f"User {user.id} upgraded to paid ({plan}, subscr_id={subscr_id}, txn={txn_type})")


def _handle_subscription_cancelled(params: dict, db: Session):
    subscr_id = params.get("subscr_id", "")

    user = db.query(models.User).filter(
        models.User.paypal_subscription_id == subscr_id
    ).first()
    if not user:
        user = _get_user_from_ipn(params, db)
    if not user:
        return

    user.is_paid             = False
    user.subscription_status = "cancelled"
    user.subscription_plan   = "free"
    db.commit()
    logger.info(f"User {user.id} downgraded (subscr_id={subscr_id} cancelled/expired)")


def _handle_subscription_failed(params: dict, db: Session):
    subscr_id = params.get("subscr_id", "")

    user = db.query(models.User).filter(
        models.User.paypal_subscription_id == subscr_id
    ).first()
    if user:
        user.subscription_status = "payment_failed"
        db.commit()
        logger.info(f"User {user.id} payment failed (subscr_id={subscr_id})")
