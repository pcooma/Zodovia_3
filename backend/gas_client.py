"""
Google Apps Script HTTP client — replaces SQLAlchemy / PostgreSQL data layer.

All user data is stored in Google Sheets (in the configured Drive folder).
FastAPI calls the deployed GAS Web App for every read/write operation.

Required env vars:
  GAS_URL     — deployed Web App URL  (https://script.google.com/macros/s/.../exec)
  GAS_API_KEY — shared secret set in GAS Script Properties
"""
import json
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

GAS_URL     = os.getenv("GAS_URL", "")
GAS_API_KEY = os.getenv("GAS_API_KEY", "")

_TIMEOUT = 35.0   # GAS can be slow on cold start


# ── Transport helpers ──────────────────────────────────────────────

async def _get(action: str, **params) -> Any:
    all_params = {"action": action, "api_key": GAS_API_KEY, **{k: v for k, v in params.items() if v is not None}}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.get(GAS_URL, params=all_params, follow_redirects=True)
        resp.raise_for_status()
    result = resp.json()
    if not result.get("success"):
        raise RuntimeError(f"GAS error [{action}]: {result.get('error', 'unknown')}")
    return result.get("data")


async def _post(action: str, **body) -> Any:
    payload = {"action": action, "api_key": GAS_API_KEY,
               **{k: v for k, v in body.items() if v is not None}}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.post(GAS_URL, json=payload, follow_redirects=True)
        resp.raise_for_status()
    result = resp.json()
    if not result.get("success"):
        raise RuntimeError(f"GAS error [{action}]: {result.get('error', 'unknown')}")
    return result.get("data")


# ── UserRecord — attribute-compatible wrapper ──────────────────────

class UserRecord:
    """Wraps a GAS user dict with attribute access matching the old ORM model."""

    def __init__(self, data: dict):
        d = data or {}
        self.id                     = d.get("id")
        self.email                  = d.get("email")
        self.password_hash          = d.get("password_hash")
        self.name                   = d.get("name")
        self.birth_date             = d.get("birth_date")
        self.birth_time             = d.get("birth_time")
        self.birth_city             = d.get("birth_city")
        self.birth_lat              = d.get("birth_lat")
        self.birth_lon              = d.get("birth_lon")
        self.birth_timezone         = d.get("birth_timezone")
        self.sun_sign               = d.get("sun_sign")
        self.moon_sign              = d.get("moon_sign")
        self.rising_sign            = d.get("rising_sign")
        self.reading_focus          = d.get("reading_focus")
        self.life_context           = d.get("life_context")
        self.life_event             = d.get("life_event")
        self.gender                 = d.get("gender")
        self.marital_status         = d.get("marital_status")
        self.occupation             = d.get("occupation")
        self.job_type               = d.get("job_type")
        self.education_level        = d.get("education_level")
        self.current_location       = d.get("current_location")
        self.wellness_goal          = d.get("wellness_goal")
        self.life_phase             = d.get("life_phase")
        self.primary_intention      = d.get("primary_intention")
        self.sensitive_flags        = d.get("sensitive_flags")
        self.profile_summary        = d.get("profile_summary")
        self.profile_updated_at     = d.get("profile_updated_at")
        self.profiling_stage        = int(d.get("profiling_stage") or 0)
        self.current_streak         = int(d.get("current_streak") or 0)
        self.longest_streak         = int(d.get("longest_streak") or 0)
        self.last_active_date       = d.get("last_active_date")
        self.total_active_days      = int(d.get("total_active_days") or 0)
        self.is_superuser           = bool(d.get("is_superuser"))
        self.free_uses              = int(d.get("free_uses") or 0)
        self.trial_uses             = int(d.get("trial_uses") or 0)
        self.is_paid                = bool(d.get("is_paid"))
        self.paypal_subscription_id = d.get("paypal_subscription_id")
        self.subscription_status    = d.get("subscription_status") or "free"
        self.subscription_plan      = d.get("subscription_plan") or "free"
        self.created_at             = d.get("created_at")
        self.last_login             = d.get("last_login")


class ChartRecord:
    def __init__(self, data: dict):
        d = data or {}
        self.id           = d.get("id")
        self.user_id      = d.get("user_id")
        self.chart_data   = d.get("chart_data")
        self.free_reading = d.get("free_reading")
        self.full_reading = d.get("full_reading")
        self.created_at   = d.get("created_at")


class ForecastRecord:
    def __init__(self, data: dict):
        d = data or {}
        self.id          = d.get("id")
        self.user_id     = d.get("user_id")
        self.period_type = d.get("period_type")
        self.period_key  = d.get("period_key")
        self.content     = d.get("content")
        self.created_at  = d.get("created_at")


class DailyRecord:
    def __init__(self, data: dict):
        d = data or {}
        self.id         = d.get("id")
        self.user_id    = d.get("user_id")
        self.date       = d.get("date")
        self.content    = d.get("content")
        self.intention  = d.get("intention")
        self.email_sent = bool(d.get("email_sent"))
        self.created_at = d.get("created_at")


class PaymentRecord:
    def __init__(self, data: dict):
        d = data or {}
        self.id                  = d.get("id")
        self.user_id             = d.get("user_id")
        self.user_email          = d.get("user_email")
        self.plan                = d.get("plan")
        self.amount_lkr          = d.get("amount_lkr")
        self.slip_drive_id       = d.get("slip_drive_id")
        self.slip_view_url       = d.get("slip_view_url")
        self.slip_filename       = d.get("slip_filename")
        self.extracted_name      = d.get("extracted_name")
        self.extracted_bank      = d.get("extracted_bank")
        self.extracted_reference = d.get("extracted_reference")
        self.extracted_amount    = d.get("extracted_amount")
        self.extracted_date      = d.get("extracted_date")
        self.extracted_currency  = d.get("extracted_currency")
        self.raw_extraction      = d.get("raw_extraction")
        self.status              = d.get("status", "pending")
        self.admin_notes         = d.get("admin_notes")
        self.reviewed_at         = d.get("reviewed_at")
        self.created_at          = d.get("created_at")


# ── Users ──────────────────────────────────────────────────────────

async def get_user_by_email(email: str) -> Optional[UserRecord]:
    data = await _get("get_user_by_email", email=email)
    return UserRecord(data) if data else None


async def get_user_by_id(user_id: int) -> Optional[UserRecord]:
    data = await _get("get_user_by_id", id=user_id)
    return UserRecord(data) if data else None


async def get_user_by_sub_id(sub_id: str) -> Optional[UserRecord]:
    data = await _get("get_user_by_sub_id", sub_id=sub_id)
    return UserRecord(data) if data else None


async def create_user(email: str, password_hash: str, name: str,
                      is_superuser: bool = False, is_paid: bool = False,
                      subscription_status: str = "free") -> UserRecord:
    data = await _post("create_user", email=email, password_hash=password_hash,
                       name=name, is_superuser=is_superuser, is_paid=is_paid,
                       subscription_status=subscription_status)
    return UserRecord(data)


async def update_user(user_id: int, **fields) -> Optional[UserRecord]:
    data = await _post("update_user", id=user_id, fields=fields)
    return UserRecord(data) if data else None


async def delete_user(user_id: int) -> dict:
    return await _post("delete_user", id=user_id)


async def get_all_users(limit: int = 500, offset: int = 0) -> list[dict]:
    return await _get("get_all_users", limit=limit, offset=offset) or []


async def get_stats() -> dict:
    return await _get("get_stats") or {}


# ── Password Resets ────────────────────────────────────────────────

async def create_pw_reset(user_id: int, token: str, expires_at: str) -> dict:
    return await _post("create_pw_reset", user_id=user_id, token=token, expires_at=expires_at)


async def get_pw_reset(token: str) -> Optional[dict]:
    return await _get("get_pw_reset", token=token)


async def invalidate_pw_resets(user_id: int) -> dict:
    return await _post("invalidate_pw_resets", user_id=user_id)


async def mark_pw_reset_used(token: str) -> dict:
    return await _post("mark_pw_reset_used", token=token)


# ── Registration IPs ───────────────────────────────────────────────

async def log_reg_ip(ip_address: str, user_id: Optional[int] = None) -> dict:
    return await _post("log_reg_ip", ip_address=ip_address, user_id=user_id)


async def get_reg_ip_count(ip: str, days: int = 14) -> int:
    result = await _get("get_reg_ip_count", ip=ip, days=days)
    return int((result or {}).get("count", 0))


async def cleanup_reg_ips(cutoff: str) -> dict:
    return await _post("cleanup_reg_ips", cutoff=cutoff)


# ── Birth Charts ───────────────────────────────────────────────────

async def get_chart(user_id: int) -> Optional[ChartRecord]:
    data = await _get("get_chart", user_id=user_id)
    return ChartRecord(data) if data else None


async def save_chart(user_id: int, chart_data: Optional[dict] = None,
                     free_reading: Optional[str] = None,
                     full_reading: Optional[str] = None) -> ChartRecord:
    data = await _post("save_chart", user_id=user_id,
                       chart_data=chart_data,
                       free_reading=free_reading,
                       full_reading=full_reading)
    return ChartRecord(data)


async def update_chart(user_id: int, **fields) -> Optional[ChartRecord]:
    data = await _post("update_chart", user_id=user_id, fields=fields)
    return ChartRecord(data) if data else None


async def delete_chart(user_id: int) -> dict:
    return await _post("delete_chart", user_id=user_id)


# ── Compatibility Reports ──────────────────────────────────────────

async def save_compat_report(user_id: int, person2_name: str,
                             person2_birth_date: str, person2_birth_time: str,
                             person2_birth_city: str, person2_sun_sign: str,
                             relationship_type: str, report: str) -> dict:
    return await _post("save_compat",
                       user_id=user_id, person2_name=person2_name,
                       person2_birth_date=person2_birth_date,
                       person2_birth_time=person2_birth_time,
                       person2_birth_city=person2_birth_city,
                       person2_sun_sign=person2_sun_sign,
                       relationship_type=relationship_type, report=report)


async def count_compat_reports(user_id: int) -> int:
    result = await _get("count_compat", user_id=user_id)
    return int((result or {}).get("count", 0))


# ── Forecasts ──────────────────────────────────────────────────────

async def get_forecast(user_id: int, period_type: str, period_key: str) -> Optional[ForecastRecord]:
    data = await _get("get_forecast", user_id=user_id,
                      period_type=period_type, period_key=period_key)
    return ForecastRecord(data) if data else None


async def save_forecast(user_id: int, period_type: str,
                        period_key: str, content: str) -> dict:
    return await _post("save_forecast", user_id=user_id, period_type=period_type,
                       period_key=period_key, content=content)


async def delete_forecasts(user_id: int,
                           period_keys: Optional[list] = None) -> dict:
    return await _post("delete_forecasts", user_id=user_id, period_keys=period_keys)


# ── Daily Horoscopes ───────────────────────────────────────────────

async def get_daily_horoscope(user_id: int, date: str) -> Optional[DailyRecord]:
    data = await _get("get_daily", user_id=user_id, date=date)
    return DailyRecord(data) if data else None


async def save_daily_horoscope(user_id: int, date: str, content: str,
                               intention: Optional[str] = None) -> DailyRecord:
    data = await _post("save_daily", user_id=user_id, date=date,
                       content=content, intention=intention)
    return DailyRecord(data)


async def update_daily_horoscope(user_id: int, date: str, **fields) -> Optional[DailyRecord]:
    data = await _post("update_daily", user_id=user_id, date=date, fields=fields)
    return DailyRecord(data) if data else None


async def delete_daily_horoscope(user_id: int, date: str) -> dict:
    return await _post("delete_daily", user_id=user_id, date=date)


async def get_paid_users_for_daily() -> list[UserRecord]:
    rows = await _get("get_paid_users_for_daily") or []
    return [UserRecord(r) for r in rows]


# ── Payment Records ────────────────────────────────────────────────

async def save_payment_slip_to_drive(base64_data: str, mime_type: str, filename: str) -> dict:
    return await _post("save_payment_slip", base64=base64_data, mime_type=mime_type, filename=filename)


async def create_payment_record(**kwargs) -> PaymentRecord:
    data = await _post("create_payment_record", **kwargs)
    return PaymentRecord(data)


async def get_all_payment_records(status: str = "all") -> list:
    rows = await _get("get_all_payment_records", status=status) or []
    return [PaymentRecord(r) for r in rows]


async def update_payment_record(record_id: int, **fields) -> Optional[PaymentRecord]:
    data = await _post("update_payment_record", id=record_id, fields=fields)
    return PaymentRecord(data) if data else None
