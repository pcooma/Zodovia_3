from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from .. import models
from ..schemas import AdminUserSummary, AdminUserDetail
from ..auth import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_superuser(current_user: models.User = Depends(get_current_user)) -> models.User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser access required")
    return current_user


def _format_dt(dt) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d %H:%M") if hasattr(dt, "strftime") else str(dt)


def _user_to_summary(user: models.User, chart: models.BirthChart | None) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "is_paid": user.is_paid,
        "subscription_status": user.subscription_status,
        "sun_sign": user.sun_sign,
        "moon_sign": user.moon_sign,
        "rising_sign": user.rising_sign,
        "birth_city": user.birth_city,
        "birth_date": user.birth_date,
        "reading_focus": user.reading_focus,
        "life_event": user.life_event,
        "created_at": _format_dt(user.created_at),
        "last_login": _format_dt(user.last_login),
        "has_chart": chart is not None,
        "has_full_reading": chart is not None and bool(chart.full_reading),
        "gender": user.gender,
        "marital_status": user.marital_status,
        "occupation": user.occupation,
        "current_location": user.current_location,
    }


@router.get("/users", response_model=List[AdminUserSummary])
def list_users(
    db: Session = Depends(get_db),
    _su: models.User = Depends(_require_superuser),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    """Return users (superuser only). Supports limit/offset pagination."""
    users = db.query(models.User).order_by(models.User.id.desc()).offset(offset).limit(limit).all()
    user_ids = [u.id for u in users]
    charts = {
        c.user_id: c
        for c in db.query(models.BirthChart).filter(models.BirthChart.user_id.in_(user_ids)).all()
    }
    return [_user_to_summary(u, charts.get(u.id)) for u in users]


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    _su: models.User = Depends(_require_superuser),
):
    """Return a single user's full data including readings (superuser only)."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    chart = db.query(models.BirthChart).filter(
        models.BirthChart.user_id == user.id
    ).first()

    data = _user_to_summary(user, chart)
    data["life_context"] = user.life_context
    data["free_reading"] = chart.free_reading if chart else None
    data["full_reading"] = chart.full_reading if chart else None
    data["job_type"] = user.job_type
    data["education_level"] = user.education_level
    return data


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    _su: models.User = Depends(_require_superuser),
):
    """Quick summary stats (superuser only)."""
    total = db.query(models.User).count()
    paid = db.query(models.User).filter(models.User.is_paid == True).count()
    charts = db.query(models.BirthChart).count()
    compat = db.query(models.CompatibilityReport).count()
    return {
        "total_users": total,
        "paid_users": paid,
        "free_users": total - paid,
        "charts_generated": charts,
        "compatibility_reports": compat,
    }
