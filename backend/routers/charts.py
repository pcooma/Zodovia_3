from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, timedelta
from ..database import get_db
from .. import models
from ..schemas import (
    ChartResponse, HoroscopeResponse, AskStarsRequest, AskStarsResponse, ForecastResponse
)
from ..auth import get_current_user, get_paid_user, get_paid_or_trial_user, check_ai_rate_limit, increment_trial_use
from ..astrology import geocode_city, calculate_chart
from ..claude_ai import (
    generate_birth_chart_reading,
    generate_daily_horoscope,
    generate_weekly_forecast,
    generate_monthly_forecast,
    answer_astrology_question,
)


def _update_streak(user: models.User, db: Session) -> None:
    """Update consecutive-day streak for engagement tracking."""
    today_str = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()

    if user.last_active_date == today_str:
        return  # already counted today

    if user.last_active_date == yesterday_str:
        user.current_streak = (user.current_streak or 0) + 1
    else:
        user.current_streak = 1  # streak broken or first visit

    user.longest_streak = max(user.longest_streak or 0, user.current_streak)
    user.total_active_days = (user.total_active_days or 0) + 1
    user.last_active_date = today_str
    db.commit()

router = APIRouter(prefix="/api/charts", tags=["charts"])


def _get_chart_data_for_user(user: models.User, db: Session) -> dict:
    """Return stored chart_data from DB if available, otherwise calculate fresh.
    Avoids redundant Swiss Ephemeris computation on every AI request."""
    stored = db.query(models.BirthChart).filter(
        models.BirthChart.user_id == user.id
    ).first()
    if stored and stored.chart_data:
        return stored.chart_data
    return calculate_chart(
        user.name, user.birth_date, user.birth_time,
        user.birth_lat, user.birth_lon, user.birth_timezone
    )


def _get_or_create_chart(user: models.User, db: Session, is_paid: bool) -> tuple:
    """Return existing chart or compute + store a new one."""
    if not user.birth_date:
        raise HTTPException(status_code=400, detail="Please submit your birth data first")

    existing = db.query(models.BirthChart).filter(
        models.BirthChart.user_id == user.id
    ).first()

    # Build shared kwargs for Claude — depends only on user profile, not chart_data
    reading_kwargs = dict(
        name=user.name,
        reading_focus=user.reading_focus,
        life_context=user.life_context,
        life_event=user.life_event,
        birth_date=user.birth_date,
        gender=user.gender,
        marital_status=user.marital_status,
        occupation=user.occupation,
        job_type=user.job_type,
        education_level=user.education_level,
        current_location=user.current_location,
        wellness_goal=user.wellness_goal,
        life_phase=user.life_phase,
        primary_intention=user.primary_intention,
        sensitive_flags=user.sensitive_flags,
        profile_summary=user.profile_summary,
    )

    if existing:
        # If paid and full_reading is missing, generate it now (lazy upgrade)
        if is_paid and not existing.full_reading:
            chart_data = calculate_chart(
                user.name, user.birth_date, user.birth_time,
                user.birth_lat, user.birth_lon, user.birth_timezone
            )
            existing.full_reading = generate_birth_chart_reading(
                chart_data, is_paid=True, **reading_kwargs
            )
            db.commit()
            db.refresh(existing)
        # Use stored chart_data — avoids redundant ephemeris recalculation
        return existing, existing.chart_data

    # First time — compute and generate the appropriate reading tier
    chart_data = calculate_chart(
        user.name, user.birth_date, user.birth_time,
        user.birth_lat, user.birth_lon, user.birth_timezone
    )

    if is_paid:
        free_reading = None
        full_reading = generate_birth_chart_reading(
            chart_data, is_paid=True, **reading_kwargs
        )
    else:
        free_reading = generate_birth_chart_reading(
            chart_data, is_paid=False, **reading_kwargs
        )
        full_reading = None

    chart = models.BirthChart(
        user_id=user.id,
        chart_data=chart_data,
        free_reading=free_reading,
        full_reading=full_reading,
    )
    db.add(chart)
    db.commit()
    db.refresh(chart)
    return chart, chart_data


@router.get("/my-chart", response_model=ChartResponse)
def get_my_chart(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    chart, chart_data = _get_or_create_chart(current_user, db, current_user.is_paid or current_user.is_superuser)

    reading = chart.full_reading if current_user.is_paid else chart.free_reading

    return ChartResponse(
        sun_sign=chart_data["sun_sign"],
        moon_sign=chart_data["moon_sign"],
        rising_sign=chart_data["rising_sign"],
        rising_degree=chart_data.get("rising_degree", 0.0),
        planets=chart_data["planets"],
        free_reading=reading,
        is_paid=current_user.is_paid or current_user.is_superuser,
    )


@router.post("/ask-stars", response_model=AskStarsResponse)
def ask_stars(
    data: AskStarsRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_paid_or_trial_user)
):
    """Answer a personal life question using the user's birth chart. Paid users only."""
    if not current_user.birth_date:
        raise HTTPException(status_code=400, detail="Please submit your birth data first")

    check_ai_rate_limit(current_user.id, "ask_stars")

    chart_data = _get_chart_data_for_user(current_user, db)

    answer = answer_astrology_question(
        chart_data,
        current_user.name,
        data.question,
        wellness_goal=current_user.wellness_goal,
        life_phase=current_user.life_phase,
        primary_intention=current_user.primary_intention,
        reading_focus=current_user.reading_focus,
        sensitive_flags=current_user.sensitive_flags,
        profile_summary=current_user.profile_summary,
    )
    increment_trial_use(current_user, db)
    return AskStarsResponse(answer=answer, free_uses_remaining=None)


@router.get("/horoscope/today", response_model=HoroscopeResponse)
def get_today_horoscope(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_paid_or_trial_user)
):
    today_str = date.today().isoformat()
    _update_streak(current_user, db)

    # Return cached horoscope if already generated today
    existing = db.query(models.DailyHoroscope).filter(
        models.DailyHoroscope.user_id == current_user.id,
        models.DailyHoroscope.date == today_str
    ).first()

    if existing:
        return HoroscopeResponse(date=today_str, content=existing.content)

    if not current_user.birth_date:
        raise HTTPException(status_code=400, detail="Please submit your birth data first")

    chart_data = _get_chart_data_for_user(current_user, db)

    content, intention = generate_daily_horoscope(
        chart_data,
        date.today(),
        wellness_goal=current_user.wellness_goal,
        life_phase=current_user.life_phase,
        primary_intention=current_user.primary_intention,
        reading_focus=current_user.reading_focus,
        sensitive_flags=current_user.sensitive_flags,
        profile_summary=current_user.profile_summary,
    )

    horoscope = models.DailyHoroscope(
        user_id=current_user.id,
        date=today_str,
        content=content,
        intention=intention or None,
    )
    db.add(horoscope)
    db.commit()

    increment_trial_use(current_user, db)
    return HoroscopeResponse(date=today_str, content=content)


@router.get("/intention/today")
def get_today_intention(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Return today's personalised daily intention (cached with horoscope).
    Cached results are always free — only new AI generation consumes a trial use."""
    today_str = date.today().isoformat()

    existing = db.query(models.DailyHoroscope).filter(
        models.DailyHoroscope.user_id == current_user.id,
        models.DailyHoroscope.date == today_str
    ).first()

    # Serve cached intention for free — user already paid with the horoscope trial use
    if existing and existing.intention:
        return {"date": today_str, "intention": existing.intention}

    # Need to generate — apply trial/paid gate only here
    is_paid = current_user.is_paid or current_user.is_superuser
    if not is_paid and (current_user.trial_uses or 0) >= 5:
        raise HTTPException(status_code=402, detail="trial_exhausted")

    if not current_user.birth_date:
        raise HTTPException(status_code=400, detail="Please submit your birth data first")

    chart_data = _get_chart_data_for_user(current_user, db)

    horoscope_text, intention = generate_daily_horoscope(
        chart_data,
        date.today(),
        wellness_goal=current_user.wellness_goal,
        life_phase=current_user.life_phase,
        primary_intention=current_user.primary_intention,
        reading_focus=current_user.reading_focus,
        sensitive_flags=current_user.sensitive_flags,
        profile_summary=current_user.profile_summary,
    )

    if existing:
        existing.intention = intention or None
        db.commit()
    else:
        record = models.DailyHoroscope(
            user_id=current_user.id,
            date=today_str,
            content=horoscope_text,
            intention=intention or None,
        )
        db.add(record)
        try:
            db.commit()
        except Exception:
            db.rollback()  # race: horoscope/today created the record first
        else:
            increment_trial_use(current_user, db)

    return {"date": today_str, "intention": intention or ""}


def _get_or_create_forecast(
    user: models.User,
    db: Session,
    period_type: str,
    period_key: str,
    week_start: date | None = None,
    month_date: date | None = None,
    count_trial: bool = True,
) -> models.Forecast:
    """Return a cached forecast or generate + store a new one."""
    if not user.birth_date:
        raise HTTPException(status_code=400, detail="Please submit your birth data first")

    existing = db.query(models.Forecast).filter(
        models.Forecast.user_id == user.id,
        models.Forecast.period_type == period_type,
        models.Forecast.period_key == period_key,
    ).first()

    if existing:
        return existing

    chart_data = _get_chart_data_for_user(user, db)

    if period_type == "week":
        content = generate_weekly_forecast(
            chart_data,
            week_start=week_start or date.today(),
            wellness_goal=user.wellness_goal,
            life_phase=user.life_phase,
            primary_intention=user.primary_intention,
            reading_focus=user.reading_focus,
            sensitive_flags=user.sensitive_flags,
            profile_summary=user.profile_summary,
        )
    else:
        content = generate_monthly_forecast(
            chart_data,
            month_date=month_date or date.today(),
            wellness_goal=user.wellness_goal,
            life_phase=user.life_phase,
            primary_intention=user.primary_intention,
            reading_focus=user.reading_focus,
            sensitive_flags=user.sensitive_flags,
            profile_summary=user.profile_summary,
        )

    forecast = models.Forecast(
        user_id=user.id,
        period_type=period_type,
        period_key=period_key,
        content=content,
    )
    db.add(forecast)
    db.commit()
    db.refresh(forecast)
    if count_trial:
        increment_trial_use(user, db)
    return forecast


@router.get("/forecast/week", response_model=ForecastResponse)
def get_weekly_forecast(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_paid_or_trial_user)
):
    """Return this week's personalised forecast (cached per ISO week)."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday of current week
    iso_year, iso_week, _ = today.isocalendar()
    period_key = f"{iso_year}-W{iso_week:02d}"

    forecast = _get_or_create_forecast(
        current_user, db,
        period_type="week",
        period_key=period_key,
        week_start=week_start,
    )
    return ForecastResponse(
        period_type="week",
        period_key=period_key,
        content=forecast.content,
    )


@router.get("/forecast/month", response_model=ForecastResponse)
def get_monthly_forecast(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_paid_or_trial_user)
):
    """Return this month's personalised forecast (cached per calendar month)."""
    today = date.today()
    period_key = today.strftime("%Y-%m")

    forecast = _get_or_create_forecast(
        current_user, db,
        period_type="month",
        period_key=period_key,
        month_date=today,
    )
    return ForecastResponse(
        period_type="month",
        period_key=period_key,
        content=forecast.content,
    )
