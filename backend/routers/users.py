import time
import uuid
import logging
from collections import defaultdict
from datetime import datetime, date, timedelta, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from .. import gas_client
from ..gas_client import UserRecord
from ..schemas import (
    UserRegister, UserLogin, TokenResponse, UserResponse, BirthDataSubmit,
    ForgotPasswordRequest, ResetPasswordRequest,
)
from ..auth import hash_password, verify_password, create_access_token, get_current_user
from ..astrology import geocode_city, geocode_preview, geocode_suggestions, timezone_from_coords, calculate_chart
from ..claude_ai import generate_profile_summary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/users", tags=["users"])

# ── Rate limiter ───────────────────────────────────────────────────
_rl_store: dict[str, list] = defaultdict(list)
_RL_WINDOW    = 60
_RL_MAX_AUTH  = 10
_IP_REG_DAYS  = 14
_MAX_REGS_PER_IP = 5


def _get_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For")
    return fwd.split(",")[0].strip() if fwd else request.client.host


def _check_rate_limit(ip: str) -> None:
    now   = time.time()
    calls = [t for t in _rl_store[ip] if now - t < _RL_WINDOW]
    _rl_store[ip] = calls
    if len(calls) >= _RL_MAX_AUTH:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Too many attempts. Please wait a minute.")
    _rl_store[ip].append(now)


def _bg_profile_summary(user_id: int, chart_data: dict, name: str,
                        wellness_goal, life_phase, primary_intention,
                        reading_focus=None, sensitive_flags=None) -> None:
    import asyncio
    try:
        summary = generate_profile_summary(
            name=name, chart_data=chart_data,
            wellness_goal=wellness_goal, life_phase=life_phase,
            primary_intention=primary_intention, reading_focus=reading_focus,
            sensitive_flags=sensitive_flags,
        )
        asyncio.run(gas_client.update_user(user_id,
            profile_summary=summary,
            profile_updated_at=datetime.utcnow().isoformat(),
        ))
        logger.info("Profile summary updated for user %s", user_id)
    except Exception as e:
        logger.warning("Profile summary failed for user %s: %s", user_id, e)


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(request: Request, data: UserRegister):
    _check_rate_limit(_get_ip(request))

    existing = await gas_client.get_user_by_email(data.email)
    if existing:
        raise HTTPException(status_code=400,
            detail="This email is already registered. Please sign in or use a different email address.")

    client_ip = _get_ip(request)
    cutoff    = (datetime.utcnow() - timedelta(days=_IP_REG_DAYS)).isoformat()
    await gas_client.cleanup_reg_ips(cutoff)

    ip_count = await gas_client.get_reg_ip_count(client_ip, _IP_REG_DAYS)
    if ip_count >= _MAX_REGS_PER_IP:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many accounts created from this location. Please try again in 2 weeks.")

    user = await gas_client.create_user(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
    )
    await gas_client.log_reg_ip(client_ip, user.id)

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user, from_attributes=True))


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, data: UserLogin):
    _check_rate_limit(_get_ip(request))
    user = await gas_client.get_user_by_email(data.email)
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    await gas_client.update_user(user.id, last_login=datetime.utcnow().isoformat())
    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user, from_attributes=True))


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserRecord = Depends(get_current_user)):
    return UserResponse.model_validate(current_user, from_attributes=True)


@router.get("/geocode-preview")
def geocode_city_preview(city: str = Query(..., min_length=2, max_length=200)):
    result = geocode_preview(city)
    if not result:
        raise HTTPException(status_code=404, detail=f"Could not find location: {city}")
    return result


@router.get("/city-suggestions")
def city_suggestions(q: str = Query(..., min_length=2, max_length=200)):
    return geocode_suggestions(q)


@router.post("/birth-data", response_model=UserResponse)
async def submit_birth_data(
    data: BirthDataSubmit,
    background_tasks: BackgroundTasks,
    current_user: UserRecord = Depends(get_current_user),
):
    if data.birth_lat is not None and data.birth_lon is not None:
        lat, lon = data.birth_lat, data.birth_lon
        tz_str   = timezone_from_coords(lat, lon)
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
        raise HTTPException(status_code=400,
            detail="Could not calculate chart. Check your birth details and try again.")

    # Determine if birth/profile data changed
    birth_changed = (
        current_user.birth_date != data.birth_date
        or current_user.birth_time != data.birth_time
        or current_user.birth_city != data.birth_city
        or (data.birth_lat  is not None and current_user.birth_lat  != data.birth_lat)
        or (data.birth_lon  is not None and current_user.birth_lon  != data.birth_lon)
        or (data.reading_focus    is not None and current_user.reading_focus    != data.reading_focus)
        or (data.life_context     is not None and current_user.life_context     != data.life_context)
        or (data.life_event       is not None and current_user.life_event       != data.life_event)
        or (data.gender           is not None and current_user.gender           != data.gender)
        or (data.marital_status   is not None and current_user.marital_status   != data.marital_status)
        or (data.occupation       is not None and current_user.occupation       != data.occupation)
        or (data.job_type         is not None and current_user.job_type         != data.job_type)
        or (data.education_level  is not None and current_user.education_level  != data.education_level)
        or (data.current_location is not None and current_user.current_location != data.current_location)
        or (data.wellness_goal    is not None and current_user.wellness_goal    != data.wellness_goal)
        or (data.life_phase       is not None and current_user.life_phase       != data.life_phase)
        or (data.primary_intention is not None and current_user.primary_intention != data.primary_intention)
        or (data.sensitive_flags  is not None and current_user.sensitive_flags  != data.sensitive_flags)
    ) if current_user.birth_date else True   # always True for first submission

    # Build update dict
    updates: dict = dict(
        birth_date=data.birth_date, birth_time=data.birth_time,
        birth_city=data.birth_city, birth_lat=lat, birth_lon=lon,
        birth_timezone=tz_str,
        sun_sign=chart["sun_sign"], moon_sign=chart["moon_sign"], rising_sign=chart["rising_sign"],
    )
    for field in ("reading_focus","life_context","life_event","gender","marital_status",
                  "occupation","job_type","education_level","current_location",
                  "wellness_goal","life_phase","primary_intention","sensitive_flags"):
        val = getattr(data, field, None)
        if val is not None:
            updates[field] = val

    if birth_changed:
        updates["profile_summary"]    = None
        updates["profile_updated_at"] = None
        # Invalidate cached forecasts and today's horoscope
        today        = date.today()
        iso_y, iso_w, _ = today.isocalendar()
        week_key     = f"{iso_y}-W{iso_w:02d}"
        month_key    = today.strftime("%Y-%m")
        await gas_client.delete_forecasts(current_user.id, [week_key, month_key])
        await gas_client.delete_daily_horoscope(current_user.id, today.isoformat())
        await gas_client.delete_chart(current_user.id)

    updated_user = await gas_client.update_user(current_user.id, **updates)

    if birth_changed or not current_user.profile_summary:
        background_tasks.add_task(
            _bg_profile_summary,
            user_id=current_user.id,
            chart_data=chart,
            name=name,
            wellness_goal=updates.get("wellness_goal", current_user.wellness_goal),
            life_phase=updates.get("life_phase", current_user.life_phase),
            primary_intention=updates.get("primary_intention", current_user.primary_intention),
            reading_focus=updates.get("reading_focus", current_user.reading_focus),
            sensitive_flags=updates.get("sensitive_flags", current_user.sensitive_flags),
        )

    return UserResponse.model_validate(updated_user, from_attributes=True)


@router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest):
    from ..email_service import send_password_reset_email

    user = await gas_client.get_user_by_email(data.email)
    if not user:
        return {"status": "ok"}

    await gas_client.invalidate_pw_resets(user.id)

    token      = str(uuid.uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    await gas_client.create_pw_reset(user.id, token, expires_at)
    send_password_reset_email(user.email, user.name, token)
    return {"status": "ok"}


@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest):
    record = await gas_client.get_pw_reset(data.token)
    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")

    if datetime.now(timezone.utc).isoformat() > record["expires_at"]:
        await gas_client.mark_pw_reset_used(data.token)
        raise HTTPException(status_code=400,
            detail="This reset link has expired. Please request a new one.")

    user = await gas_client.get_user_by_id(record["user_id"])
    if not user:
        raise HTTPException(status_code=400, detail="Invalid reset link.")

    await gas_client.update_user(user.id, password_hash=hash_password(data.new_password))
    await gas_client.mark_pw_reset_used(data.token)
    return {"status": "ok"}


@router.post("/refresh-profile")
async def refresh_profile(
    background_tasks: BackgroundTasks,
    current_user: UserRecord = Depends(get_current_user),
):
    if not current_user.birth_date:
        raise HTTPException(status_code=400, detail="Please submit your birth data first")

    from ..astrology import calculate_chart as _calc
    stored = await gas_client.get_chart(current_user.id)
    chart_data = (
        stored.chart_data if stored and stored.chart_data
        else _calc(current_user.name, current_user.birth_date, current_user.birth_time,
                   current_user.birth_lat, current_user.birth_lon, current_user.birth_timezone)
    )
    background_tasks.add_task(
        _bg_profile_summary,
        user_id=current_user.id, chart_data=chart_data, name=current_user.name,
        wellness_goal=current_user.wellness_goal, life_phase=current_user.life_phase,
        primary_intention=current_user.primary_intention,
        reading_focus=current_user.reading_focus, sensitive_flags=current_user.sensitive_flags,
    )
    return {"status": "Profile summary regeneration scheduled"}
