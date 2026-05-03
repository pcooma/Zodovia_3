from fastapi import APIRouter, Depends, HTTPException
from datetime import date, timedelta
from .. import gas_client
from ..gas_client import UserRecord
from ..schemas import ChartResponse, HoroscopeResponse, AskStarsRequest, AskStarsResponse, ForecastResponse
from ..auth import get_current_user, get_paid_or_trial_user, check_ai_rate_limit, increment_trial_use
from ..astrology import calculate_chart
from ..claude_ai import (
    generate_birth_chart_reading, generate_daily_horoscope,
    generate_weekly_forecast, generate_monthly_forecast, answer_astrology_question,
)

router = APIRouter(prefix="/api/charts", tags=["charts"])


async def _update_streak(user: UserRecord) -> None:
    today_str     = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    if user.last_active_date == today_str:
        return
    if user.last_active_date == yesterday_str:
        new_streak = (user.current_streak or 0) + 1
    else:
        new_streak = 1
    new_longest = max(user.longest_streak or 0, new_streak)
    await gas_client.update_user(user.id,
        current_streak=new_streak, longest_streak=new_longest,
        total_active_days=(user.total_active_days or 0) + 1,
        last_active_date=today_str,
    )


async def _get_chart_data(user: UserRecord) -> dict:
    stored = await gas_client.get_chart(user.id)
    if stored and stored.chart_data:
        return stored.chart_data
    return calculate_chart(user.name, user.birth_date, user.birth_time,
                           user.birth_lat, user.birth_lon, user.birth_timezone)


async def _get_or_create_chart(user: UserRecord, is_paid: bool):
    if not user.birth_date:
        raise HTTPException(status_code=400, detail="Please submit your birth data first")

    existing = await gas_client.get_chart(user.id)

    reading_kwargs = dict(
        name=user.name, reading_focus=user.reading_focus, life_context=user.life_context,
        life_event=user.life_event, birth_date=user.birth_date, gender=user.gender,
        marital_status=user.marital_status, occupation=user.occupation,
        job_type=user.job_type, education_level=user.education_level,
        current_location=user.current_location, wellness_goal=user.wellness_goal,
        life_phase=user.life_phase, primary_intention=user.primary_intention,
        sensitive_flags=user.sensitive_flags, profile_summary=user.profile_summary,
    )

    if existing:
        if is_paid and not existing.full_reading:
            chart_data   = calculate_chart(user.name, user.birth_date, user.birth_time,
                                           user.birth_lat, user.birth_lon, user.birth_timezone)
            full_reading = generate_birth_chart_reading(chart_data, is_paid=True, **reading_kwargs)
            existing     = await gas_client.update_chart(user.id, full_reading=full_reading)
        return existing, existing.chart_data

    chart_data = calculate_chart(user.name, user.birth_date, user.birth_time,
                                 user.birth_lat, user.birth_lon, user.birth_timezone)
    if is_paid:
        free_r, full_r = None, generate_birth_chart_reading(chart_data, is_paid=True, **reading_kwargs)
    else:
        free_r, full_r = generate_birth_chart_reading(chart_data, is_paid=False, **reading_kwargs), None

    chart = await gas_client.save_chart(user.id, chart_data=chart_data,
                                        free_reading=free_r, full_reading=full_r)
    return chart, chart_data


@router.get("/my-chart", response_model=ChartResponse)
async def get_my_chart(current_user: UserRecord = Depends(get_current_user)):
    is_paid = current_user.is_paid or current_user.is_superuser
    chart, chart_data = await _get_or_create_chart(current_user, is_paid)
    reading = chart.full_reading if is_paid else chart.free_reading
    return ChartResponse(
        sun_sign=chart_data["sun_sign"], moon_sign=chart_data["moon_sign"],
        rising_sign=chart_data["rising_sign"],
        rising_degree=chart_data.get("rising_degree", 0.0),
        planets=chart_data["planets"],
        free_reading=reading,
        is_paid=is_paid,
    )


@router.post("/ask-stars", response_model=AskStarsResponse)
async def ask_stars(
    data: AskStarsRequest,
    current_user: UserRecord = Depends(get_paid_or_trial_user),
):
    if not current_user.birth_date:
        raise HTTPException(status_code=400, detail="Please submit your birth data first")
    check_ai_rate_limit(current_user.id, "ask_stars")

    chart_data = await _get_chart_data(current_user)
    answer = answer_astrology_question(
        chart_data, current_user.name, data.question,
        wellness_goal=current_user.wellness_goal, life_phase=current_user.life_phase,
        primary_intention=current_user.primary_intention,
        reading_focus=current_user.reading_focus, sensitive_flags=current_user.sensitive_flags,
        profile_summary=current_user.profile_summary,
    )
    await increment_trial_use(current_user)
    return AskStarsResponse(answer=answer, free_uses_remaining=None)


@router.get("/horoscope/today", response_model=HoroscopeResponse)
async def get_today_horoscope(current_user: UserRecord = Depends(get_paid_or_trial_user)):
    today_str = date.today().isoformat()
    await _update_streak(current_user)

    existing = await gas_client.get_daily_horoscope(current_user.id, today_str)
    if existing:
        return HoroscopeResponse(date=today_str, content=existing.content)

    if not current_user.birth_date:
        raise HTTPException(status_code=400, detail="Please submit your birth data first")

    chart_data         = await _get_chart_data(current_user)
    content, intention = generate_daily_horoscope(
        chart_data, date.today(),
        wellness_goal=current_user.wellness_goal, life_phase=current_user.life_phase,
        primary_intention=current_user.primary_intention,
        reading_focus=current_user.reading_focus, sensitive_flags=current_user.sensitive_flags,
        profile_summary=current_user.profile_summary,
    )
    await gas_client.save_daily_horoscope(current_user.id, today_str, content, intention=intention)
    await increment_trial_use(current_user)
    return HoroscopeResponse(date=today_str, content=content)


@router.get("/intention/today")
async def get_today_intention(current_user: UserRecord = Depends(get_current_user)):
    today_str = date.today().isoformat()
    existing  = await gas_client.get_daily_horoscope(current_user.id, today_str)

    if existing and existing.intention:
        return {"date": today_str, "intention": existing.intention}

    is_paid = current_user.is_paid or current_user.is_superuser
    if not is_paid and (current_user.trial_uses or 0) >= 5:
        raise HTTPException(status_code=402, detail="trial_exhausted")
    if not current_user.birth_date:
        raise HTTPException(status_code=400, detail="Please submit your birth data first")

    chart_data            = await _get_chart_data(current_user)
    horoscope_text, intention = generate_daily_horoscope(
        chart_data, date.today(),
        wellness_goal=current_user.wellness_goal, life_phase=current_user.life_phase,
        primary_intention=current_user.primary_intention,
        reading_focus=current_user.reading_focus, sensitive_flags=current_user.sensitive_flags,
        profile_summary=current_user.profile_summary,
    )

    if existing:
        await gas_client.update_daily_horoscope(current_user.id, today_str, intention=intention)
    else:
        await gas_client.save_daily_horoscope(current_user.id, today_str,
                                              horoscope_text, intention=intention)
        await increment_trial_use(current_user)

    return {"date": today_str, "intention": intention or ""}


async def _get_or_create_forecast(user: UserRecord, period_type: str, period_key: str,
                                   week_start=None, month_date=None, count_trial: bool = True):
    if not user.birth_date:
        raise HTTPException(status_code=400, detail="Please submit your birth data first")

    existing = await gas_client.get_forecast(user.id, period_type, period_key)
    if existing:
        return existing

    chart_data = await _get_chart_data(user)
    kwargs = dict(
        wellness_goal=user.wellness_goal, life_phase=user.life_phase,
        primary_intention=user.primary_intention, reading_focus=user.reading_focus,
        sensitive_flags=user.sensitive_flags, profile_summary=user.profile_summary,
    )
    if period_type == "week":
        content = generate_weekly_forecast(chart_data, week_start=week_start or date.today(), **kwargs)
    else:
        content = generate_monthly_forecast(chart_data, month_date=month_date or date.today(), **kwargs)

    await gas_client.save_forecast(user.id, period_type, period_key, content)
    if count_trial:
        await increment_trial_use(user)
    return await gas_client.get_forecast(user.id, period_type, period_key)


@router.get("/forecast/week", response_model=ForecastResponse)
async def get_weekly_forecast(current_user: UserRecord = Depends(get_paid_or_trial_user)):
    today      = date.today()
    week_start = today - timedelta(days=today.weekday())
    iso_y, iso_w, _ = today.isocalendar()
    period_key = f"{iso_y}-W{iso_w:02d}"
    forecast = await _get_or_create_forecast(current_user, "week", period_key, week_start=week_start)
    return ForecastResponse(period_type="week", period_key=period_key, content=forecast.content)


@router.get("/forecast/month", response_model=ForecastResponse)
async def get_monthly_forecast(current_user: UserRecord = Depends(get_paid_or_trial_user)):
    today      = date.today()
    period_key = today.strftime("%Y-%m")
    forecast = await _get_or_create_forecast(current_user, "month", period_key, month_date=today)
    return ForecastResponse(period_type="month", period_key=period_key, content=forecast.content)
