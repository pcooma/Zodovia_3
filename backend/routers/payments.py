import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import models
from ..auth import get_current_user
from ..database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])

# Switch providers with one env var: paypal | payhere
# Default to payhere for Sri Lanka deployments
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "payhere").lower()

# ── PayPal config ─────────────────────────────────────────────────────────────
PAYPAL_MONTHLY_BUTTON_ID = os.getenv("PAYPAL_MONTHLY_BUTTON_ID", "5UCX7JGEEJ3QJ")
PAYPAL_YEARLY_BUTTON_ID  = os.getenv("PAYPAL_YEARLY_BUTTON_ID",  "F88PZH4KYH6T2")
PAYPAL_BUSINESS_EMAIL    = os.getenv("PAYPAL_BUSINESS_EMAIL", "").lower().strip()
PAYPAL_IPN_VERIFY_URL    = "https://ipnpb.paypal.com/cgi-bin/webscr"

# ── PayHere config (Sri Lanka) ────────────────────────────────────────────────
PAYHERE_MERCHANT_ID     = os.getenv("PAYHERE_MERCHANT_ID", "")
PAYHERE_MERCHANT_SECRET = os.getenv("PAYHERE_MERCHANT_SECRET", "")
PAYHERE_SANDBOX         = os.getenv("PAYHERE_SANDBOX", "false").lower() == "true"
PAYHERE_BASE_URL        = (
    "https://sandbox.payhere.lk" if PAYHERE_SANDBOX else "https://www.payhere.lk"
)
PAYHERE_NOTIFY_URL      = os.getenv("PAYHERE_NOTIFY_URL",  "https://zodovia.com/api/payments/webhook")
PAYHERE_RETURN_URL      = os.getenv("PAYHERE_RETURN_URL",  "https://zodovia.com/dashboard?activated=1")
PAYHERE_CANCEL_URL      = os.getenv("PAYHERE_CANCEL_URL",  "https://zodovia.com/pricing")

# LKR plan amounts (shown to Sri Lankan users)
_PLAN_LKR = {
    "monthly": {"amount": "990.00",   "recurrence": "1 Month", "items": "Zodovia Premium Monthly"},
    "yearly":  {"amount": "4990.00",  "recurrence": "1 Year",  "items": "Zodovia Premium Yearly"},
}

# USD amounts (for verification, PayPal)
_EXPECTED_AMOUNTS_USD = {
    "monthly": 3.99,
    "yearly":  29.99,
}


# ── Shared endpoint: checkout URL / params ────────────────────────────────────

@router.get("/checkout-url")
async def get_checkout_url(
    plan: str = "monthly",
    current_user: models.User = Depends(get_current_user),
):
    """Return checkout details for whichever provider is active."""
    if plan not in ("monthly", "yearly"):
        plan = "monthly"

    if PAYMENT_PROVIDER == "payhere":
        params = _build_payhere_params(plan, current_user)
        return {
            "checkout_url": f"{PAYHERE_BASE_URL}/pay/checkout",
            "method":       "POST",
            "params":       params,
        }

    # PayPal — simple redirect
    button_id = PAYPAL_MONTHLY_BUTTON_ID if plan == "monthly" else PAYPAL_YEARLY_BUTTON_ID
    return {
        "checkout_url": (
            f"https://www.paypal.com/cgi-bin/webscr"
            f"?cmd=_s-xclick&hosted_button_id={button_id}"
        ),
        "method": "GET",
    }


# ── Unified webhook ───────────────────────────────────────────────────────────

@router.post("/webhook")
async def payment_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Routes to the active provider's IPN handler."""
    if PAYMENT_PROVIDER == "payhere":
        return await _handle_payhere_webhook(request, db)
    return await _handle_paypal_webhook(request, db)


# ── PayHere ───────────────────────────────────────────────────────────────────

def _payhere_hash(merchant_id: str, order_id: str, amount: str,
                  currency: str, secret: str) -> str:
    """MD5(merchant_id + order_id + amount + currency + MD5(secret).upper()).upper()"""
    secret_hash = hashlib.md5(secret.encode()).hexdigest().upper()
    raw = f"{merchant_id}{order_id}{amount}{currency}{secret_hash}"
    return hashlib.md5(raw.encode()).hexdigest().upper()


def _build_payhere_params(plan: str, user: models.User) -> dict:
    info      = _PLAN_LKR[plan]
    order_id  = f"{user.email}:{plan}:{int(time.time())}"
    amount    = info["amount"]
    currency  = "LKR"

    name_parts = (user.name or "").split(maxsplit=1)
    first_name = name_parts[0] if name_parts else ""
    last_name  = name_parts[1] if len(name_parts) > 1 else ""

    params = {
        "merchant_id":       PAYHERE_MERCHANT_ID,
        "return_url":        PAYHERE_RETURN_URL,
        "cancel_url":        PAYHERE_CANCEL_URL,
        "notify_url":        PAYHERE_NOTIFY_URL,
        "order_id":          order_id,
        "items":             info["items"],
        "currency":          currency,
        # For recurring, amount=0 and specify first_payment/recurring_amount
        "amount":            "0.00",
        "first_payment":     amount,
        "recurring_amount":  amount,
        "duration":          "Forever",
        "recurrence":        info["recurrence"],
        "customer_first_name": first_name,
        "customer_last_name":  last_name,
        "customer_email":    user.email,
        "custom_1":          plan,   # echo back in notify for plan detection
    }

    if PAYHERE_MERCHANT_ID and PAYHERE_MERCHANT_SECRET:
        params["hash"] = _payhere_hash(
            PAYHERE_MERCHANT_ID, order_id, amount, currency, PAYHERE_MERCHANT_SECRET
        )

    return params


def _verify_payhere_notify(params: dict) -> bool:
    """
    Verify PayHere IPN notification signature.
    md5sig = MD5(merchant_id+order_id+payhere_amount+payhere_currency+MD5(secret).upper()+status_code).upper()
    """
    if not PAYHERE_MERCHANT_SECRET:
        logger.warning("PayHere: PAYHERE_MERCHANT_SECRET not set — skipping verification")
        return False

    received_sig = params.get("md5sig", "").upper()
    if not received_sig:
        return False

    merchant_id   = params.get("merchant_id", "")
    order_id      = params.get("order_id", "")
    amount        = params.get("payhere_amount", "")
    currency      = params.get("payhere_currency", "")
    status_code   = params.get("status_code", "")

    secret_hash = hashlib.md5(PAYHERE_MERCHANT_SECRET.encode()).hexdigest().upper()
    raw = f"{merchant_id}{order_id}{amount}{currency}{secret_hash}{status_code}"
    expected = hashlib.md5(raw.encode()).hexdigest().upper()

    return hmac.compare_digest(expected, received_sig)


async def _handle_payhere_webhook(request: Request, db: Session):
    raw_body = await request.body()

    try:
        params = dict(urllib.parse.parse_qsl(raw_body.decode("utf-8")))
    except Exception:
        logger.warning("PayHere IPN: failed to parse body")
        return {"status": "ok"}

    if not _verify_payhere_notify(params):
        logger.warning("PayHere IPN: signature verification failed — discarding")
        return {"status": "ok"}

    status_code = params.get("status_code", "")
    order_id    = params.get("order_id", "")
    logger.info(f"PayHere IPN: status_code={status_code} order_id={order_id!r}")

    if status_code == "2":  # 2 = success
        await run_in_threadpool(_handle_payhere_payment_success, params, db)
    elif status_code in ("-1", "-2", "-3"):  # cancelled, failed, chargedback
        await run_in_threadpool(_handle_payhere_payment_failed, params, db)

    return {"status": "ok"}


def _handle_payhere_payment_success(params: dict, db: Session):
    order_id   = params.get("order_id", "")
    payment_id = str(params.get("payment_id", ""))

    # order_id format: "email:plan:timestamp"
    parts = order_id.split(":", 2)
    if len(parts) < 2:
        logger.warning(f"PayHere: unexpected order_id format: {order_id!r}")
        return

    email = parts[0]
    plan  = parts[1] if parts[1] in ("monthly", "yearly") else "monthly"

    # Also accept plan from custom_1 field if present
    if params.get("custom_1") in ("monthly", "yearly"):
        plan = params["custom_1"]

    amount   = params.get("payhere_amount", "0")
    currency = params.get("payhere_currency", "LKR")

    # Basic amount sanity check for LKR
    if currency == "LKR":
        expected_lkr = float(_PLAN_LKR[plan]["amount"])
        try:
            paid_amount = float(amount)
        except (ValueError, TypeError):
            paid_amount = 0
        if paid_amount > 0 and paid_amount < expected_lkr * 0.5:
            logger.warning(
                f"PayHere: amount {paid_amount} LKR far below expected "
                f"{expected_lkr} LKR for plan={plan} — discarding"
            )
            return

    user = _get_user_by_email(email, db)
    if not user:
        user = db.query(models.User).filter(
            models.User.paypal_subscription_id == payment_id
        ).first()
    if not user:
        logger.warning(f"PayHere: no user found for order_id={order_id!r}")
        return

    user.is_paid                = True
    user.paypal_subscription_id = payment_id   # reuses existing field
    user.subscription_status    = "active"
    user.subscription_plan      = plan
    user.trial_uses             = 0
    db.commit()
    logger.info(
        f"User {user.id} upgraded via PayHere "
        f"(plan={plan}, payment_id={payment_id}, amount={amount} {currency})"
    )


def _handle_payhere_payment_failed(params: dict, db: Session):
    order_id   = params.get("order_id", "")
    payment_id = str(params.get("payment_id", ""))
    status     = params.get("status_code", "")

    email = order_id.split(":", 1)[0] if ":" in order_id else ""
    user = _get_user_by_email(email, db)
    if not user:
        user = db.query(models.User).filter(
            models.User.paypal_subscription_id == payment_id
        ).first()
    if user:
        user.subscription_status = "payment_failed"
        db.commit()
        logger.info(
            f"User {user.id} PayHere payment failed/cancelled "
            f"(status_code={status}, payment_id={payment_id})"
        )


# ── PayPal IPN ────────────────────────────────────────────────────────────────

async def _handle_paypal_webhook(request: Request, db: Session):
    raw_body = await request.body()

    if not await _verify_paypal_ipn(raw_body):
        logger.warning("PayPal IPN: verification failed — discarding")
        return {"status": "ok"}

    params   = dict(urllib.parse.parse_qsl(raw_body.decode("utf-8")))
    txn_type = params.get("txn_type", "")
    logger.info(f"PayPal IPN: txn_type={txn_type}")

    if PAYPAL_BUSINESS_EMAIL:
        receiver = params.get("receiver_email", "").lower().strip()
        if receiver != PAYPAL_BUSINESS_EMAIL:
            logger.warning(f"PayPal IPN: receiver mismatch ({receiver!r}) — discarding")
            return {"status": "ok"}

    if txn_type in ("subscr_signup", "subscr_payment", "subscr_modify"):
        await run_in_threadpool(_handle_subscription_active, params, db)
    elif txn_type in ("subscr_cancel", "subscr_eot"):
        await run_in_threadpool(_handle_subscription_cancelled, params, db)
    elif txn_type == "subscr_failed":
        await run_in_threadpool(_handle_subscription_failed, params, db)

    return {"status": "ok"}


async def _verify_paypal_ipn(raw_body: bytes) -> bool:
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
    txn_type = params.get("txn_type", "")
    if txn_type != "subscr_payment":
        return True

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

    expected = _EXPECTED_AMOUNTS_USD.get(plan)
    if expected and amount < expected * 0.5:
        logger.warning(f"PayPal IPN: amount {amount} far below expected {expected} for {plan}")
        return False

    return True


def _get_user_by_email(email: str, db: Session):
    if not email:
        return None
    return db.query(models.User).filter(
        models.User.email == email.lower().strip()
    ).first()


def _handle_subscription_active(params: dict, db: Session):
    subscr_id = params.get("subscr_id", "")
    plan      = params.get("custom", "monthly")
    txn_type  = params.get("txn_type", "")

    if plan not in ("monthly", "yearly"):
        plan = "monthly"

    if not _verify_payment_amount(params, plan):
        logger.warning(f"PayPal IPN: amount verification failed for subscr_id={subscr_id}, discarding")
        return

    user = None
    if txn_type == "subscr_payment" and subscr_id:
        user = db.query(models.User).filter(
            models.User.paypal_subscription_id == subscr_id
        ).first()
    if not user:
        user = _get_user_by_email(params.get("payer_email", ""), db)
    if not user:
        logger.warning(f"PayPal IPN: no user found for subscr_id={subscr_id}")
        return

    user.is_paid                = True
    user.paypal_subscription_id = subscr_id
    user.subscription_status    = "active"
    user.subscription_plan      = plan
    user.trial_uses             = 0
    db.commit()
    logger.info(f"User {user.id} upgraded via PayPal ({plan}, subscr_id={subscr_id}, txn={txn_type})")


def _handle_subscription_cancelled(params: dict, db: Session):
    subscr_id = params.get("subscr_id", "")
    user = db.query(models.User).filter(
        models.User.paypal_subscription_id == subscr_id
    ).first()
    if not user:
        user = _get_user_by_email(params.get("payer_email", ""), db)
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
        logger.info(f"User {user.id} PayPal payment failed (subscr_id={subscr_id})")
