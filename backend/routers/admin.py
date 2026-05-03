import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from typing import List
from .. import gas_client
from ..gas_client import UserRecord
from ..schemas import AdminUserSummary, AdminUserDetail
from ..auth import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def _require_superuser(
    current_user: UserRecord = Depends(get_current_user),
) -> UserRecord:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser access required")
    return current_user


def _user_summary(user: UserRecord, has_chart: bool, has_full_reading: bool) -> dict:
    return {
        "id": user.id, "email": user.email, "name": user.name,
        "is_paid": user.is_paid, "subscription_status": user.subscription_status,
        "sun_sign": user.sun_sign, "moon_sign": user.moon_sign, "rising_sign": user.rising_sign,
        "birth_city": user.birth_city, "birth_date": user.birth_date,
        "reading_focus": user.reading_focus, "life_event": user.life_event,
        "created_at": user.created_at, "last_login": user.last_login,
        "has_chart": has_chart, "has_full_reading": has_full_reading,
        "gender": user.gender, "marital_status": user.marital_status,
        "occupation": user.occupation, "current_location": user.current_location,
    }


@router.get("/users", response_model=List[AdminUserSummary])
async def list_users(
    _su: UserRecord = Depends(_require_superuser),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    users = await gas_client.get_all_users(limit=limit, offset=offset)
    result = []
    for u_dict in users:
        u = UserRecord(u_dict)
        chart = await gas_client.get_chart(u.id)
        result.append(_user_summary(u,
            has_chart=chart is not None,
            has_full_reading=bool(chart and chart.full_reading),
        ))
    return result


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_user_detail(
    user_id: int,
    _su: UserRecord = Depends(_require_superuser),
):
    user = await gas_client.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    chart = await gas_client.get_chart(user.id)
    data  = _user_summary(user,
        has_chart=chart is not None,
        has_full_reading=bool(chart and chart.full_reading),
    )
    data["life_context"]  = user.life_context
    data["free_reading"]  = chart.free_reading  if chart else None
    data["full_reading"]  = chart.full_reading  if chart else None
    data["job_type"]      = user.job_type
    data["education_level"] = user.education_level
    return data


@router.get("/stats")
async def get_stats(_su: UserRecord = Depends(_require_superuser)):
    return await gas_client.get_stats()


@router.get("/payments")
async def list_payment_records(
    status: str = Query(default="pending"),
    _su: UserRecord = Depends(_require_superuser),
):
    records = await gas_client.get_all_payment_records(status=status)
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "user_email": r.user_email,
            "plan": r.plan,
            "amount_lkr": r.amount_lkr,
            "slip_view_url": r.slip_view_url,
            "slip_filename": r.slip_filename,
            "extracted_name": r.extracted_name,
            "extracted_bank": r.extracted_bank,
            "extracted_reference": r.extracted_reference,
            "extracted_amount": r.extracted_amount,
            "extracted_date": r.extracted_date,
            "extracted_currency": r.extracted_currency,
            "status": r.status,
            "admin_notes": r.admin_notes,
            "reviewed_at": r.reviewed_at,
            "created_at": r.created_at,
        }
        for r in records
    ]


@router.post("/payments/{record_id}/approve")
async def approve_payment(
    record_id: int,
    _su: UserRecord = Depends(_require_superuser),
):
    now = datetime.datetime.utcnow().isoformat()
    record = await gas_client.update_payment_record(record_id, status="approved", reviewed_at=now)
    if not record:
        raise HTTPException(404, "Payment record not found")

    if record.user_id:
        plan = record.plan or "one_time"
        await gas_client.update_user(
            int(record.user_id),
            is_paid=True,
            subscription_plan=plan,
            subscription_status="active",
        )
    return {"ok": True}


@router.post("/payments/{record_id}/reject")
async def reject_payment(
    record_id: int,
    notes: str = Body(default="", embed=True),
    _su: UserRecord = Depends(_require_superuser),
):
    now = datetime.datetime.utcnow().isoformat()
    record = await gas_client.update_payment_record(
        record_id, status="rejected", admin_notes=notes, reviewed_at=now
    )
    if not record:
        raise HTTPException(404, "Payment record not found")
    return {"ok": True}
