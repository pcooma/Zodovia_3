from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models
from ..schemas import CompatibilityRequest, CompatibilityResponse
from ..auth import get_current_user, check_free_limit, increment_free_use, FREE_LIMIT, check_ai_rate_limit
from ..astrology import geocode_city, timezone_from_coords, calculate_chart
from ..claude_ai import generate_compatibility_reading

router = APIRouter(prefix="/api/compatibility", tags=["compatibility"])


@router.post("", response_model=CompatibilityResponse)
def check_compatibility(
    data: CompatibilityRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Generate a compatibility reading between the current user and another person."""
    if not current_user.birth_date:
        raise HTTPException(status_code=400, detail="Please submit your birth data first")

    # Validate limits before the expensive AI call — only increment on success
    check_free_limit(current_user)
    check_ai_rate_limit(current_user.id, "compat")

    # Use exact coordinates if provided, otherwise geocode the city name
    if data.person2_birth_lat is not None and data.person2_birth_lon is not None:
        lat2 = data.person2_birth_lat
        lon2 = data.person2_birth_lon
        tz2 = timezone_from_coords(lat2, lon2)
    else:
        geo2 = geocode_city(data.person2_birth_city)
        if not geo2:
            raise HTTPException(
                status_code=400,
                detail=f"Could not find city: {data.person2_birth_city}"
            )
        lat2, lon2, tz2 = geo2

    # Use stored chart_data for current user if available — avoids redundant ephemeris calculation
    stored = db.query(models.BirthChart).filter(models.BirthChart.user_id == current_user.id).first()
    if stored and stored.chart_data:
        chart1 = stored.chart_data
    else:
        chart1 = calculate_chart(
            current_user.name,
            current_user.birth_date,
            current_user.birth_time,
            current_user.birth_lat,
            current_user.birth_lon,
            current_user.birth_timezone,
        )
    chart2 = calculate_chart(
        data.person2_name,
        data.person2_birth_date,
        data.person2_birth_time,
        lat2,
        lon2,
        tz2,
    )

    # Generate the compatibility report
    # Paid users get Opus + adaptive thinking; free users get Sonnet to control costs
    report = generate_compatibility_reading(
        chart1, current_user.name,
        chart2, data.person2_name,
        data.relationship_type,
        is_paid=current_user.is_paid or current_user.is_superuser,
        sensitive_flags=current_user.sensitive_flags,
        wellness_goal=current_user.wellness_goal,
        life_phase=current_user.life_phase,
        primary_intention=current_user.primary_intention,
        reading_focus=current_user.reading_focus,
        profile_summary=current_user.profile_summary,
    )

    # Increment free use counter after successful generation
    new_count = increment_free_use(current_user, db)

    # Persist for history
    saved = models.CompatibilityReport(
        user_id=current_user.id,
        person2_name=data.person2_name,
        person2_birth_date=data.person2_birth_date,
        person2_birth_time=data.person2_birth_time,
        person2_birth_city=data.person2_birth_city,
        person2_sun_sign=chart2["sun_sign"],
        relationship_type=data.relationship_type,
        report=report,
    )
    db.add(saved)
    db.commit()

    remaining = None if current_user.is_paid else (FREE_LIMIT - new_count)
    return CompatibilityResponse(
        person2_name=data.person2_name,
        person2_sun_sign=chart2["sun_sign"],
        relationship_type=data.relationship_type,
        report=report,
        free_uses_remaining=remaining,
    )
