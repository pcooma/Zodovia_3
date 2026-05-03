import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse

import anthropic
import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from .. import gas_client
from ..gas_client import UserRecord
from ..auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])

PAYMENT_PROVIDER         = os.getenv("PAYMENT_PROVIDER", "payhere").lower()
PAYPAL_MONTHLY_BUTTON_ID = os.getenv("PAYPAL_MONTHLY_BUTTON_ID", "5UCX7JGEEJ3QJ")
PAYPAL_YEARLY_BUTTON_ID  = os.getenv("PAYPAL_YEARLY_BUTTON_ID",  "F88PZH4KYH6T2")
PAYPAL_BUSINESS_EMAIL    = os.getenv("PAYPAL_BUSINESS_EMAIL", "").lower().strip()
PAYPAL_IPN_VERIFY_URL    = "https://ipnpb.paypal.com/cgi-bin/webscr"

PAYHERE_MERCHANT_ID     = os.getenv("PAYHERE_MERCHANT_ID", "")
PAYHERE_MERCHANT_SECRET = os.getenv("PAYHERE_MERCHANT_SECRET", "")
PAYHERE_SANDBOX         = os.getenv("PAYHERE_SANDBOX", "false").lower() == "true"
PAYHERE_BASE_URL        = "https://sandbox.payhere.lk" if PAYHERE_SANDBOX else "https://www.payhere.lk"
PAYHERE_NOTIFY_URL      = os.getenv("PAYHERE_NOTIFY_URL",  "https://zodovia.com/api/payments/webhook")
PAYHERE_RETURN_URL      = os.getenv("PAYHERE_RETURN_URL",  "https://zodovia.com/dashboard?activated=1")
PAYHERE_CANCEL_URL      = os.getenv("PAYHERE_CANCEL_URL",  "https://zodovia.com/pricing")

_PLAN_LKR = {
    "one_time": {"amount": "300.00",  "recurrence": None,      "items": "Zodovia One-Time Premium"},
    "monthly":  {"amount": "990.00",  "recurrence": "1 Month", "items": "Zodovia Premium Monthly"},
    "yearly":   {"amount": "4990.00", "recurrence": "1 Year",  "items": "Zodovia Premium Yearly"},
}
_EXPECTED_USD = {"monthly": 3.99, "yearly": 29.99}

BANK_DETAILS = {
    "name":           "Pramuditha Coomasaru",
    "bank":           "Bank of Ceylon (BOC)",
    "branch":         "Kalutara",
    "account_number": "9379707",
    "whatsapp":       "+94741251212",
    "whatsapp_link":  "https://wa.me/94741251212",
}

PLAN_AMOUNTS = {
    "one_time": {"amount": 300,  "label": "One-Time Premium Access"},
    "monthly":  {"amount": 990,  "label": "Monthly Premium"},
    "yearly":   {"amount": 4990, "label": "Yearly Premium"},
}

_ALLOWED_MIME = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB


@router.get("/bank-details")
async def get_bank_details():
    return {**BANK_DETAILS, "plans": PLAN_AMOUNTS}


@router.post("/bank-slip")
async def submit_bank_slip(
    file: UploadFile = File(...),
    plan: str = Form("one_time"),
    current_user: UserRecord = Depends(get_current_user),
):
    if plan not in PLAN_AMOUNTS:
        plan = "one_time"

    content_type = (file.content_type or "image/jpeg").split(";")[0].strip()
    if content_type not in _ALLOWED_MIME:
        raise HTTPException(400, "Only JPEG, PNG, GIF or WEBP images are accepted")

    file_bytes = await file.read()
    if len(file_bytes) > _MAX_FILE_BYTES:
        raise HTTPException(400, "File too large. Maximum size is 5 MB")

    # Analyze slip with Claude (fail-safe — proceed even if analysis fails)
    extracted: dict = {}
    try:
        extracted = await _analyze_slip(file_bytes, content_type)
    except Exception as exc:
        logger.warning(f"Slip analysis failed for user {current_user.id}: {exc}")

    # Upload image to Google Drive via GAS
    b64 = base64.b64encode(file_bytes).decode()
    drive_result = await gas_client.save_payment_slip_to_drive(
        b64, content_type, file.filename or "slip.jpg"
    )

    # Persist payment record
    plan_info = PLAN_AMOUNTS[plan]
    record = await gas_client.create_payment_record(
        user_id=current_user.id,
        user_email=current_user.email,
        plan=plan,
        amount_lkr=plan_info["amount"],
        slip_drive_id=drive_result.get("drive_id", ""),
        slip_view_url=drive_result.get("view_url", ""),
        slip_filename=file.filename or "slip",
        extracted_name=extracted.get("payer_name", ""),
        extracted_bank=extracted.get("bank_name", ""),
        extracted_reference=extracted.get("transaction_reference", ""),
        extracted_amount=str(extracted.get("amount", "")),
        extracted_date=str(extracted.get("date", "")),
        extracted_currency=extracted.get("currency", "LKR"),
        raw_extraction=extracted,
    )

    return {
        "record_id": record.id,
        "status": "pending",
        "extracted": extracted,
        "whatsapp": BANK_DETAILS["whatsapp_link"],
        "message": (
            "Slip received! Your account will be activated within 2 business hours "
            "(9 AM – 6 PM, Mon–Sat). You can also WhatsApp us for faster activation."
        ),
    }


async def _analyze_slip(image_bytes: bytes, mime_type: str) -> dict:
    client = anthropic.AsyncAnthropic()
    b64 = base64.b64encode(image_bytes).decode()
    msg = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": mime_type, "data": b64},
                },
                {
                    "type": "text",
                    "text": (
                        "Extract payment details from this bank transfer slip. "
                        "Return ONLY a JSON object with these fields: "
                        "payer_name, bank_name, branch, transaction_reference, amount, "
                        "currency, date, beneficiary_name, beneficiary_account. "
                        "Use null for fields you cannot determine. No markdown, no explanation."
                    ),
                },
            ],
        }],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        text = text.rstrip("`").strip()
    return json.loads(text)


@router.get("/checkout-url")
async def get_checkout_url(
    plan: str = "monthly",
    current_user: UserRecord = Depends(get_current_user),
):
    if plan not in ("monthly", "yearly"):
        plan = "monthly"

    if PAYMENT_PROVIDER == "payhere":
        params = _build_payhere_params(plan, current_user)
        return {"checkout_url": f"{PAYHERE_BASE_URL}/pay/checkout", "method": "POST", "params": params}

    button_id = PAYPAL_MONTHLY_BUTTON_ID if plan == "monthly" else PAYPAL_YEARLY_BUTTON_ID
    return {
        "checkout_url": f"https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id={button_id}",
        "method": "GET",
    }


@router.post("/webhook")
async def payment_webhook(request: Request):
    if PAYMENT_PROVIDER == "payhere":
        return await _handle_payhere_webhook(request)
    return await _handle_paypal_webhook(request)


# ── PayHere ────────────────────────────────────────────────────────

def _payhere_hash(merchant_id, order_id, amount, currency, secret):
    secret_hash = hashlib.md5(secret.encode()).hexdigest().upper()
    raw = f"{merchant_id}{order_id}{amount}{currency}{secret_hash}"
    return hashlib.md5(raw.encode()).hexdigest().upper()


def _build_payhere_params(plan: str, user: UserRecord) -> dict:
    info      = _PLAN_LKR[plan]
    order_id  = f"{user.email}:{plan}:{int(time.time())}"
    amount    = info["amount"]
    name_parts = (user.name or "").split(maxsplit=1)
    params = {
        "merchant_id": PAYHERE_MERCHANT_ID, "return_url": PAYHERE_RETURN_URL,
        "cancel_url": PAYHERE_CANCEL_URL, "notify_url": PAYHERE_NOTIFY_URL,
        "order_id": order_id, "items": info["items"], "currency": "LKR",
        "amount": "0.00", "first_payment": amount, "recurring_amount": amount,
        "duration": "Forever", "recurrence": info["recurrence"],
        "customer_first_name": name_parts[0] if name_parts else "",
        "customer_last_name":  name_parts[1] if len(name_parts) > 1 else "",
        "customer_email": user.email, "custom_1": plan,
    }
    if PAYHERE_MERCHANT_ID and PAYHERE_MERCHANT_SECRET:
        params["hash"] = _payhere_hash(PAYHERE_MERCHANT_ID, order_id, amount, "LKR",
                                       PAYHERE_MERCHANT_SECRET)
    return params


def _verify_payhere_notify(params: dict) -> bool:
    if not PAYHERE_MERCHANT_SECRET:
        logger.warning("PAYHERE_MERCHANT_SECRET not set — skipping verification")
        return False
    received = params.get("md5sig", "").upper()
    if not received:
        return False
    secret_hash = hashlib.md5(PAYHERE_MERCHANT_SECRET.encode()).hexdigest().upper()
    raw = (f"{params.get('merchant_id','')}{params.get('order_id','')}"
           f"{params.get('payhere_amount','')}{params.get('payhere_currency','')}"
           f"{secret_hash}{params.get('status_code','')}")
    return hmac.compare_digest(hashlib.md5(raw.encode()).hexdigest().upper(), received)


async def _handle_payhere_webhook(request: Request):
    raw_body = await request.body()
    try:
        params = dict(urllib.parse.parse_qsl(raw_body.decode("utf-8")))
    except Exception:
        return {"status": "ok"}

    if not _verify_payhere_notify(params):
        logger.warning("PayHere IPN: signature verification failed")
        return {"status": "ok"}

    status_code = params.get("status_code", "")
    logger.info(f"PayHere IPN: status_code={status_code}")

    if status_code == "2":
        await _payhere_success(params)
    elif status_code in ("-1", "-2", "-3"):
        await _payhere_failed(params)
    return {"status": "ok"}


async def _payhere_success(params: dict):
    order_id   = params.get("order_id", "")
    payment_id = str(params.get("payment_id", ""))
    parts      = order_id.split(":", 2)
    if len(parts) < 2:
        logger.warning(f"PayHere: unexpected order_id: {order_id!r}")
        return
    email = parts[0]
    plan  = parts[1] if parts[1] in ("monthly", "yearly") else "monthly"
    if params.get("custom_1") in ("monthly", "yearly"):
        plan = params["custom_1"]

    currency = params.get("payhere_currency", "LKR")
    if currency == "LKR":
        expected = float(_PLAN_LKR[plan]["amount"])
        try:
            paid = float(params.get("payhere_amount", 0))
        except (ValueError, TypeError):
            paid = 0
        if paid > 0 and paid < expected * 0.5:
            logger.warning(f"PayHere: amount {paid} far below expected {expected} — discarding")
            return

    user = await gas_client.get_user_by_email(email)
    if not user:
        user = await gas_client.get_user_by_sub_id(payment_id)
    if not user:
        logger.warning(f"PayHere: no user for order_id={order_id!r}")
        return

    await gas_client.update_user(user.id,
        is_paid=True, paypal_subscription_id=payment_id,
        subscription_status="active", subscription_plan=plan, trial_uses=0)
    logger.info(f"User {user.id} upgraded via PayHere (plan={plan})")


async def _payhere_failed(params: dict):
    order_id   = params.get("order_id", "")
    payment_id = str(params.get("payment_id", ""))
    email      = order_id.split(":", 1)[0] if ":" in order_id else ""
    user = await gas_client.get_user_by_email(email)
    if not user:
        user = await gas_client.get_user_by_sub_id(payment_id)
    if user:
        await gas_client.update_user(user.id, subscription_status="payment_failed")
        logger.info(f"User {user.id} PayHere payment failed/cancelled")


# ── PayPal IPN ─────────────────────────────────────────────────────

async def _handle_paypal_webhook(request: Request):
    raw_body = await request.body()
    if not await _verify_paypal_ipn(raw_body):
        logger.warning("PayPal IPN: verification failed")
        return {"status": "ok"}

    params   = dict(urllib.parse.parse_qsl(raw_body.decode("utf-8")))
    txn_type = params.get("txn_type", "")
    logger.info(f"PayPal IPN: txn_type={txn_type}")

    if PAYPAL_BUSINESS_EMAIL:
        receiver = params.get("receiver_email", "").lower().strip()
        if receiver != PAYPAL_BUSINESS_EMAIL:
            logger.warning(f"PayPal IPN: receiver mismatch ({receiver!r})")
            return {"status": "ok"}

    if txn_type in ("subscr_signup", "subscr_payment", "subscr_modify"):
        await _paypal_active(params)
    elif txn_type in ("subscr_cancel", "subscr_eot"):
        await _paypal_cancelled(params)
    elif txn_type == "subscr_failed":
        await _paypal_failed(params)
    return {"status": "ok"}


async def _verify_paypal_ipn(raw_body: bytes) -> bool:
    try:
        verify_body = b"cmd=_notify-validate&" + raw_body
        async with httpx.AsyncClient(timeout=15) as c:
            resp = await c.post(PAYPAL_IPN_VERIFY_URL, content=verify_body,
                                headers={"Content-Type": "application/x-www-form-urlencoded"})
        return resp.text.strip() == "VERIFIED"
    except Exception as e:
        logger.error(f"PayPal IPN verify error: {e}")
        return False


async def _paypal_active(params: dict):
    subscr_id = params.get("subscr_id", "")
    plan      = params.get("custom", "monthly")
    txn_type  = params.get("txn_type", "")
    if plan not in ("monthly", "yearly"):
        plan = "monthly"

    if txn_type == "subscr_payment":
        currency = params.get("mc_currency", "").upper()
        if currency == "USD":
            try:
                amount = float(params.get("mc_gross", 0))
            except (ValueError, TypeError):
                amount = 0
            expected = _EXPECTED_USD.get(plan, 0)
            if amount > 0 and expected and amount < expected * 0.5:
                logger.warning(f"PayPal: amount {amount} far below expected — discarding")
                return

    user = None
    if txn_type == "subscr_payment" and subscr_id:
        user = await gas_client.get_user_by_sub_id(subscr_id)
    if not user:
        user = await gas_client.get_user_by_email(params.get("payer_email", ""))
    if not user:
        logger.warning(f"PayPal IPN: no user for subscr_id={subscr_id}")
        return

    await gas_client.update_user(user.id,
        is_paid=True, paypal_subscription_id=subscr_id,
        subscription_status="active", subscription_plan=plan, trial_uses=0)
    logger.info(f"User {user.id} upgraded via PayPal ({plan})")


async def _paypal_cancelled(params: dict):
    subscr_id = params.get("subscr_id", "")
    user = await gas_client.get_user_by_sub_id(subscr_id)
    if not user:
        user = await gas_client.get_user_by_email(params.get("payer_email", ""))
    if not user:
        return
    await gas_client.update_user(user.id,
        is_paid=False, subscription_status="cancelled", subscription_plan="free")
    logger.info(f"User {user.id} downgraded (subscr_id={subscr_id} cancelled)")


async def _paypal_failed(params: dict):
    subscr_id = params.get("subscr_id", "")
    user = await gas_client.get_user_by_sub_id(subscr_id)
    if user:
        await gas_client.update_user(user.id, subscription_status="payment_failed")
        logger.info(f"User {user.id} PayPal payment failed")
