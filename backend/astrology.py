from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from kerykeion import AstrologicalSubject
from typing import Optional
import logging

logger = logging.getLogger(__name__)

_geocoder = Nominatim(user_agent="zodovia_app_v1")
_tf = TimezoneFinder()

SIGN_EMOJIS = {
    "Ari": "♈", "Tau": "♉", "Gem": "♊", "Can": "♋",
    "Leo": "♌", "Vir": "♍", "Lib": "♎", "Sco": "♏",
    "Sag": "♐", "Cap": "♑", "Aqu": "♒", "Pis": "♓"
}

SIGN_NAMES = {
    "Ari": "Aries", "Tau": "Taurus", "Gem": "Gemini", "Can": "Cancer",
    "Leo": "Leo", "Vir": "Virgo", "Lib": "Libra", "Sco": "Scorpio",
    "Sag": "Sagittarius", "Cap": "Capricorn", "Aqu": "Aquarius", "Pis": "Pisces"
}

# Absolute start degree (0–360) of each zodiac sign
_SIGN_START_DEGREE: dict[str, float] = {
    "Ari": 0.0, "Tau": 30.0, "Gem": 60.0, "Can": 90.0,
    "Leo": 120.0, "Vir": 150.0, "Lib": 180.0, "Sco": 210.0,
    "Sag": 240.0, "Cap": 270.0, "Aqu": 300.0, "Pis": 330.0,
}

HOUSE_MEANINGS = {
    1: "Self & Identity", 2: "Money & Possessions", 3: "Communication",
    4: "Home & Family", 5: "Creativity & Romance", 6: "Health & Work",
    7: "Partnerships", 8: "Transformation", 9: "Philosophy & Travel",
    10: "Career & Status", 11: "Friends & Aspirations", 12: "Spirituality"
}

# kerykeion 4.x returns house as a string ("First_House", "Second_House", …)
_HOUSE_STR_TO_INT = {
    "First_House": 1, "Second_House": 2, "Third_House": 3,
    "Fourth_House": 4, "Fifth_House": 5, "Sixth_House": 6,
    "Seventh_House": 7, "Eighth_House": 8, "Ninth_House": 9,
    "Tenth_House": 10, "Eleventh_House": 11, "Twelfth_House": 12,
}


def geocode_city(city: str) -> Optional[tuple[float, float, str]]:
    """Returns (lat, lon, timezone_str) or None if not found."""
    try:
        location = _geocoder.geocode(city, timeout=10)
        if not location:
            return None
        lat, lon = location.latitude, location.longitude
        tz_str = _tf.timezone_at(lat=lat, lng=lon)
        if not tz_str:
            tz_str = "UTC"
        return lat, lon, tz_str
    except Exception as e:
        logger.error(f"Geocoding failed for '{city}': {e}")
        return None


def geocode_preview(city: str) -> Optional[dict]:
    """Returns resolved location details for user confirmation, or None if not found."""
    try:
        location = _geocoder.geocode(city, timeout=10)
        if not location:
            return None
        lat, lon = location.latitude, location.longitude
        tz_str = _tf.timezone_at(lat=lat, lng=lon) or "UTC"
        return {
            "resolved_name": location.address,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "timezone": tz_str,
        }
    except Exception as e:
        logger.error(f"Geocode preview failed for '{city}': {e}")
        return None


def geocode_suggestions(query: str, limit: int = 6) -> list[dict]:
    """Returns up to `limit` city suggestions for autocomplete."""
    try:
        results = _geocoder.geocode(query, exactly_one=False, limit=limit, timeout=8)
        if not results:
            return []
        out = []
        for r in results:
            parts = [p.strip() for p in r.address.split(",")]
            display = ", ".join(parts[:3]) if len(parts) > 3 else r.address
            out.append({
                "display_name": display,
                "full_address": r.address,
                "lat": round(r.latitude, 6),
                "lon": round(r.longitude, 6),
            })
        return out
    except Exception as e:
        logger.error(f"Geocode suggestions failed for '{query}': {e}")
        return []


def timezone_from_coords(lat: float, lon: float) -> str:
    """Returns timezone string for the given coordinates."""
    try:
        tz_str = _tf.timezone_at(lat=lat, lng=lon)
        return tz_str or "UTC"
    except Exception:
        return "UTC"


def calculate_chart(
    name: str,
    birth_date: str,
    birth_time: str,
    lat: float,
    lon: float,
    tz_str: str
) -> dict:
    """
    Calculate full birth chart using Kerykeion (Swiss Ephemeris).
    birth_date: "YYYY-MM-DD"
    birth_time: "HH:MM"
    Returns structured chart data dict.
    """
    year, month, day = birth_date.split("-")
    hour, minute = birth_time.split(":")

    subject = AstrologicalSubject(
        name=name,
        year=int(year),
        month=int(month),
        day=int(day),
        hour=int(hour),
        minute=int(minute),
        lat=lat,
        lng=lon,
        tz_str=tz_str,
        online=False  # use local Swiss Ephemeris data
    )

    def planet_info(planet_obj) -> dict:
        sign_short = planet_obj.sign
        raw_house = getattr(planet_obj, "house", None)
        house_num = _HOUSE_STR_TO_INT.get(str(raw_house), raw_house) if raw_house else None
        return {
            "sign": SIGN_NAMES.get(sign_short, sign_short),
            "sign_short": sign_short,
            "emoji": SIGN_EMOJIS.get(sign_short, ""),
            "degree": round(planet_obj.position, 2),
            "house": house_num,
            "retrograde": getattr(planet_obj, "retrograde", False)
        }

    planets = {
        "Sun":     planet_info(subject.sun),
        "Moon":    planet_info(subject.moon),
        "Mercury": planet_info(subject.mercury),
        "Venus":   planet_info(subject.venus),
        "Mars":    planet_info(subject.mars),
        "Jupiter": planet_info(subject.jupiter),
        "Saturn":  planet_info(subject.saturn),
        "Uranus":  planet_info(subject.uranus),
        "Neptune": planet_info(subject.neptune),
        "Pluto":   planet_info(subject.pluto),
    }

    rising_short = subject.first_house.sign
    sun_sign_short = subject.sun.sign
    sun_abs_degree = round(
        _SIGN_START_DEGREE.get(sun_sign_short, 0.0) + subject.sun.position,
        4
    )

    chart_data = {
        "sun_sign":      planets["Sun"]["sign"],
        "moon_sign":     planets["Moon"]["sign"],
        "rising_sign":   SIGN_NAMES.get(rising_short, rising_short),
        "rising_emoji":  SIGN_EMOJIS.get(rising_short, ""),
        "rising_degree": round(subject.first_house.position, 2),  # degree within sign (0–29.99)
        "sun_degree":    sun_abs_degree,  # absolute tropical degree 0–360 (for HD gate calc)
        "planets":       planets,
        "house_meanings": HOUSE_MEANINGS,
    }

    return chart_data
