import time
import uuid
import logging
from collections import defaultdict
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta, timezone
from ..database import get_db, SessionLocal
from .. import models
from ..schemas import (
    UserRegister, UserLogin, TokenResponse, UserResponse, BirthDataSubmit,
    ForgotPasswordRequest, ResetPasswordRequest,
)
from ..auth import hash_password, verify_password, create_access_token, get_current_user
from ..astrology import geocode_city, geocode_preview, geocode_suggestions, timezone_from_coords, calculate_chart
from ..claude_ai import generate_profile_summary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/users", tags=["users"])


def _bg_generate_profile_summary(user_id: int, chart_data: dict, name: str,
                                  wellness_goal: str | None, life_phase: str | None,
                                  primary_intention: str | None,
                                  reading_focus: str | None = None,
                                  sensitive_flags: list | None = None) -> None:
    """Background task: generate an AI profile summary and persist it."""
    db = SessionLocal()
    try:
        summary = generate_profile_summary(
            name=name,
            chart_data=chart_data,
            wellness_goal=wellness_goal,
            life_phase=life_phase,
            primary_intention=primary_intention,
            reading_focus=reading_focus,
            sensitive_flags=sensitive_flags,
        )
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user:
            user.profile_summary = summary
            user.profile_updated_at = datetime.utcnow()
            db.commit()
            logger.info("Profile summary updated for user %s", user_id)
    except Exception as e:
        logger.warning("Profile summary generation failed for user %s: %s", user_id, e)
    finally:
        db.close()

# ── Simple in-memory rate limiter ─────────────────────────────────────────────
_rl_store: dict[str, list] = defaultdict(list)
_RL_WINDOW = 60        # seconds
_RL_MAX_AUTH = 10      # login/register attempts per window per IP

_IP_REG_WINDOW_DAYS = 14   # how long to keep registration IP records
_MAX_REGS_PER_IP = 5       # max registrations from one IP in that window


def _get_client_ip(request: Request) -> str:
    """Return the real client IP, respecting X-Forwarded-For from Railway's proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    calls = [t for t in _rl_store[ip] if now - t < _RL_WINDOW]
    _rl_store[ip] = calls
    if len(calls) >= _RL_MAX_AUTH:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please wait a minute before trying again."
        )
    _rl_store[ip].append(now)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(request: Request, data: UserRegister, db: Session = Depends(get_db)):
    _check_rate_limit(_get_client_ip(request))

    existing = db.query(models.User).filter(models.User.email == data.email).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="This email is already registered. Please sign in or use a different email address."
        )

    client_ip = _get_client_ip(request)
    cutoff = datetime.utcnow() - timedelta(days=_IP_REG_WINDOW_DAYS)

    # Lazy cleanup: remove expired IP records while we're here
    db.query(models.RegistrationIP).filter(
        models.RegistrationIP.created_at < cutoff
    ).delete(synchronize_session=False)
    db.commit()

    # Check how many accounts have been created from this IP recently
    recent_ip_count = db.query(models.RegistrationIP).filter(
        models.RegistrationIP.ip_address == client_ip,
        models.RegistrationIP.user_id.isnot(None),
    ).count()
    if recent_ip_count >= _MAX_REGS_PER_IP:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many accounts created from this location. Please try again in 2 weeks."
        )

    user = models.User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Record this registration against the IP
    db.add(models.RegistrationIP(ip_address=client_ip, user_id=user.id))
    db.commit()

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(request: Request, data: UserLogin, db: Session = Depends(get_db)):
    _check_rate_limit(_get_client_ip(request))
    user = db.query(models.User).filter(models.User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user.last_login = datetime.utcnow()
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.get("/geocode-preview")
def geocode_city_preview(city: str = Query(..., min_length=2, max_length=200)):
    """Return the resolved location name, coordinates, and timezone for a city string.
    Used by the frontend to show a confirmation before submitting birth data.
    No authentication required."""
    result = geocode_preview(city)
    if not result:
        raise HTTPException(status_code=404, detail=f"Could not find location: {city}")
    return result


@router.get("/city-suggestions")
def city_suggestions(q: str = Query(..., min_length=2, max_length=200)):
    """Return up to 6 city name suggestions for autocomplete as the user types."""
    return geocode_suggestions(q)


@router.post("/birth-data", response_model=UserResponse)
def submit_birth_data(
    data: BirthDataSubmit,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Use exact coordinates if provided, otherwise geocode the city name
    if data.birth_lat is not None and data.birth_lon is not None:
        lat = data.birth_lat
        lon = data.birth_lon
        tz_str = timezone_from_coords(lat, lon)
    else:
        geo = geocode_city(data.birth_city)
        if not geo:
            raise HTTPException(status_code=400, detail=f"Could not find city: {data.birth_city}")
        lat, lon, tz_str = geo
    name = data.name or current_user.name

    try:
        chart = calculate_chart(name, data.birth_date, data.birth_time, lat, lon, tz_str)
    except Exception as exc:
        logger.error("Chart calculation failed: %s", exc)
        raise HTTPException(status_code=400, detail="Could not calculate chart. Check your birth details and try again.")

    # If birth data or personalisation changed, delete the old chart so
    # the chart page regenerates a reading that matches the current data.
    birth_changed = True  # default True (new user or first submission)
    existing_chart = db.query(models.BirthChart).filter(
        models.BirthChart.user_id == current_user.id
    ).first()
    if existing_chart:
        # Any meaningful change → regenerate reading so it stays accurate
        birth_changed = (
            current_user.birth_date != data.birth_date
            or current_user.birth_time != data.birth_time
            or current_user.birth_city != data.birth_city
            or (data.birth_lat is not None and current_user.birth_lat != data.birth_lat)
            or (data.birth_lon is not None and current_user.birth_lon != data.birth_lon)
            or (data.reading_focus is not None and current_user.reading_focus != data.reading_focus)
            or (data.life_context is not None and current_user.life_context != data.life_context)
            or (data.life_event is not None and current_user.life_event != data.life_event)
            or (data.gender is not None and current_user.gender != data.gender)
            or (data.marital_status is not None and current_user.marital_status != data.marital_status)
            or (data.occupation is not None and current_user.occupation != data.occupation)
            or (data.job_type is not None and current_user.job_type != data.job_type)
            or (data.education_level is not None and current_user.education_level != data.education_level)
            or (data.current_location is not None and current_user.current_location != data.current_location)
            or (data.wellness_goal is not None and current_user.wellness_goal != data.wellness_goal)
            or (data.life_phase is not None and current_user.life_phase != data.life_phase)
            or (data.primary_intention is not None and current_user.primary_intention != data.primary_intention)
            or (data.sensitive_flags is not None and current_user.sensitive_flags != data.sensitive_flags)
        )
        if birth_changed:
            db.delete(existing_chart)
        # Keep birth_changed accurate for later use

    current_user.birth_date = data.birth_date
    current_user.birth_time = data.birth_time
    current_user.birth_city = data.birth_city
    current_user.birth_lat = lat
    current_user.birth_lon = lon
    current_user.birth_timezone = tz_str
    current_user.sun_sign = chart["sun_sign"]
    current_user.moon_sign = chart["moon_sign"]
    current_user.rising_sign = chart["rising_sign"]

    # Optional personalisation context
    if data.reading_focus is not None:
        current_user.reading_focus = data.reading_focus
    if data.life_context is not None:
        current_user.life_context = data.life_context
    if data.life_event is not None:
        current_user.life_event = data.life_event

    # Optional demographics
    if data.gender is not None:
        current_user.gender = data.gender
    if data.marital_status is not None:
        current_user.marital_status = data.marital_status
    if data.occupation is not None:
        current_user.occupation = data.occupation
    if data.job_type is not None:
        current_user.job_type = data.job_type
    if data.education_level is not None:
        current_user.education_level = data.education_level
    if data.current_location is not None:
        current_user.current_location = data.current_location
    if data.wellness_goal is not None:
        current_user.wellness_goal = data.wellness_goal
    if data.life_phase is not None:
        current_user.life_phase = data.life_phase
    if data.primary_intention is not None:
        current_user.primary_intention = data.primary_intention
    if data.sensitive_flags is not None:
        current_user.sensitive_flags = data.sensitive_flags

    # Invalidate stale profile summary and cached forecasts so they regenerate with new data
    if birth_changed:
        current_user.profile_summary = None
        current_user.profile_updated_at = None
        # Delete cached forecasts for the current week and month so the next
        # request regenerates them with the updated profile context
        today = date.today()
        iso_year, iso_week, _ = today.isocalendar()
        current_week_key = f"{iso_year}-W{iso_week:02d}"
        current_month_key = today.strftime("%Y-%m")
        db.query(models.Forecast).filter(
            models.Forecast.user_id == current_user.id,
            models.Forecast.period_key.in_([current_week_key, current_month_key])
        ).delete(synchronize_session=False)
        # Invalidate today's horoscope so it regenerates with the updated profile
        db.query(models.DailyHoroscope).filter(
            models.DailyHoroscope.user_id == current_user.id,
            models.DailyHoroscope.date == today.isoformat()
        ).delete(synchronize_session=False)

    db.commit()
    db.refresh(current_user)

    # Schedule non-blocking AI profile summary generation only when needed
    if birth_changed or not current_user.profile_summary:
        background_tasks.add_task(
            _bg_generate_profile_summary,
            user_id=current_user.id,
            chart_data=chart,
            name=name,
            wellness_goal=current_user.wellness_goal,
            life_phase=current_user.life_phase,
            primary_intention=current_user.primary_intention,
            reading_focus=current_user.reading_focus,
            sensitive_flags=current_user.sensitive_flags,
        )

    return current_user


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    from ..email_service import send_password_reset_email

    user = db.query(models.User).filter(models.User.email == data.email).first()
    # Always return 200 — never reveal whether the email exists
    if not user:
        return {"status": "ok"}

    # Invalidate any existing unused tokens for this user
    db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.user_id == user.id,
        models.PasswordResetToken.used == False,  # noqa: E712
    ).update({"used": True})
    db.commit()

    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    reset_record = models.PasswordResetToken(
        user_id=user.id,
        token=token,
        expires_at=expires_at,
    )
    db.add(reset_record)
    db.commit()

    send_password_reset_email(user.email, user.name, token)
    return {"status": "ok"}


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    record = db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.token == data.token,
        models.PasswordResetToken.used == False,  # noqa: E712
    ).first()

    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")

    if datetime.now(timezone.utc) > record.expires_at:
        record.used = True
        db.commit()
        raise HTTPException(status_code=400, detail="This reset link has expired. Please request a new one.")

    user = db.query(models.User).filter(models.User.id == record.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid reset link.")

    user.password_hash = hash_password(data.new_password)
    record.used = True
    db.commit()
    return {"status": "ok"}


@router.post("/refresh-profile")
def refresh_profile_summary(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Manually trigger a profile summary regeneration for the current user."""
    if not current_user.birth_date:
        raise HTTPException(status_code=400, detail="Please submit your birth data first")

    from ..astrology import calculate_chart as _calc
    stored_chart = db.query(models.BirthChart).filter(
        models.BirthChart.user_id == current_user.id
    ).first()
    chart_data = (
        stored_chart.chart_data
        if stored_chart and stored_chart.chart_data
        else _calc(
            current_user.name, current_user.birth_date, current_user.birth_time,
            current_user.birth_lat, current_user.birth_lon, current_user.birth_timezone,
        )
    )

    background_tasks.add_task(
        _bg_generate_profile_summary,
        user_id=current_user.id,
        chart_data=chart_data,
        name=current_user.name,
        wellness_goal=current_user.wellness_goal,
        life_phase=current_user.life_phase,
        primary_intention=current_user.primary_intention,
        reading_focus=current_user.reading_focus,
        sensitive_flags=current_user.sensitive_flags,
    )
    return {"status": "Profile summary regeneration scheduled"}
