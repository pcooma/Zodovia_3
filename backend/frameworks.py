"""
frameworks.py — Multi-framework personal development synthesis

Computes numerology, Human Design type (simplified), and chakra/energy profile
from a user's existing birth data and name. No new user input required.
All calculations are deterministic and computable server-side.
"""

from datetime import date as date_cls, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# NUMEROLOGY — Pythagorean system
# ─────────────────────────────────────────────────────────────────────────────

_PYTHAGOREAN: dict[str, int] = {
    'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5, 'f': 6, 'g': 7, 'h': 8, 'i': 9,
    'j': 1, 'k': 2, 'l': 3, 'm': 4, 'n': 5, 'o': 6, 'p': 7, 'q': 8, 'r': 9,
    's': 1, 't': 2, 'u': 3, 'v': 4, 'w': 5, 'x': 6, 'y': 7, 'z': 8,
}
_VOWELS = set('aeiou')
_MASTER_NUMBERS = {11, 22, 33}


def _reduce(n: int) -> int:
    """Reduce to single digit, preserving master numbers 11, 22, 33."""
    while n > 9 and n not in _MASTER_NUMBERS:
        n = sum(int(d) for d in str(n))
    return n


def life_path_number(birth_date: str) -> int:
    """Life Path Number from YYYY-MM-DD — the core life theme."""
    digits = [int(c) for c in birth_date.replace('-', '') if c.isdigit()]
    return _reduce(sum(digits))


def expression_number(name: str) -> int:
    """Expression (Destiny) Number from full name — outer gifts and direction."""
    total = sum(_PYTHAGOREAN.get(c.lower(), 0) for c in name if c.isalpha())
    return _reduce(total)


def soul_urge_number(name: str) -> int:
    """Soul Urge (Heart's Desire) from vowels — inner motivation and longing."""
    total = sum(_PYTHAGOREAN.get(c.lower(), 0) for c in name if c.lower() in _VOWELS)
    return _reduce(total)


def personality_number(name: str) -> int:
    """Personality Number from consonants — outer mask and how others first see you."""
    total = sum(_PYTHAGOREAN.get(c.lower(), 0) for c in name
                if c.isalpha() and c.lower() not in _VOWELS)
    return _reduce(total)


_LIFE_PATH_PROFILES: dict[int, tuple[str, str]] = {
    1:  ("The Pioneer",       "natural leadership, independence, and the drive to innovate and create your own path"),
    2:  ("The Diplomat",      "deep intuition, sensitivity, the gift of partnership, and seeing harmony in all things"),
    3:  ("The Creator",       "vibrant creativity, self-expression, joy, and the natural ability to inspire and uplift"),
    4:  ("The Builder",       "discipline, reliability, methodical thinking, and the power to build lasting foundations"),
    5:  ("The Explorer",      "freedom, adaptability, restless curiosity, and an appetite for experiencing life fully"),
    6:  ("The Nurturer",      "responsibility, deep compassion, healing, and creating beauty and harmony in relationships"),
    7:  ("The Seeker",        "analytical depth, spiritual seeking, inner knowing, and a hunger for truth"),
    8:  ("The Powerhouse",    "material mastery, executive leadership, commanding presence, and the ability to manifest abundance"),
    9:  ("The Sage",          "universal compassion, wisdom, completion, and the calling to serve and give back"),
    11: ("The Illuminator",   "master intuition, spiritual insight, and the power to illuminate and inspire on a large scale"),
    22: ("The Master Builder","visionary leadership grounded in reality — the ability to turn dreams into lasting structures"),
    33: ("The Master Teacher","unconditional love, healing presence, and the calling to guide others toward their highest selves"),
}

_EXPRESSION_THEMES: dict[int, str] = {
    1:  "to lead, initiate, and stand in your own unique power",
    2:  "to bring people together, mediate, and build bridges of understanding",
    3:  "to create, communicate, and bring beauty and joy into the world",
    4:  "to build, organise, and create systems that stand the test of time",
    5:  "to explore, communicate change, and inspire freedom in others",
    6:  "to nurture, heal, and take responsibility for creating a better world",
    7:  "to seek, discover, and share deep wisdom and truth",
    8:  "to lead with authority, manifest abundance, and master the material world",
    9:  "to serve humanity, inspire through example, and complete what matters most",
    11: "to channel higher wisdom and inspire spiritual awakening in others",
    22: "to build on a grand scale — turning inspired vision into tangible reality",
    33: "to heal, teach, and embody love as a living practice",
}

_SOUL_URGE_THEMES: dict[int, str] = {
    1:  "deep down, you long to be independent, pioneering, and fully yourself",
    2:  "at your core, you crave connection, harmony, and to feel truly understood",
    3:  "your soul longs to express, create, and be seen in your full creative light",
    4:  "you yearn for security, stability, and a life built on solid ground",
    5:  "your deepest craving is freedom — to roam, explore, and never be boxed in",
    6:  "you long to love and be loved, to create a beautiful home and harmonious relationships",
    7:  "your soul seeks solitude, depth, and the truth that lives beneath the surface",
    8:  "at your core, you long for influence, recognition, and the power to shape your world",
    9:  "you are driven by a deep desire to make a meaningful difference and be truly seen as wise",
    11: "your soul craves spiritual depth, inner awakening, and a sense of higher purpose",
    22: "you long to leave a lasting mark — to build something truly meaningful for the world",
    33: "your deepest desire is to love unconditionally and be a source of healing for others",
}


# ─────────────────────────────────────────────────────────────────────────────
# HUMAN DESIGN — Simplified type via Sun gate (Rave wheel)
# ─────────────────────────────────────────────────────────────────────────────

# Canonical gate order clockwise from 0° Aries (each gate = 5.625°)
_RAVE_WHEEL: list[int] = [
    25, 17, 21, 51, 42,  3, 27, 24,  2, 23,  8, 20, 16, 35, 45, 12,
    15, 52, 39, 53, 62, 56, 31, 33,  7,  4, 29, 59, 40, 64, 47,  6,
    46, 18, 48, 57, 32, 50, 28, 44,  1, 43, 14, 34,  9,  5, 26, 11,
    10, 58, 38, 54, 61, 60, 41, 19, 13, 49, 30, 55, 37, 63, 22, 36,
]

# Gate → Human Design Type tendency (based on gate circuit classifications)
_GATE_TYPE_MAP: dict[int, str] = {
    # Integration channel gates → Manifestor / MG tendency
    20: "Manifestor", 10: "Manifestor", 34: "Manifesting Generator", 57: "Manifestor",
    # Tribal / Ego circuit → Generator / MG
    26: "Manifesting Generator", 51: "Manifesting Generator", 21: "Manifesting Generator",
    45: "Projector", 40: "Generator", 37: "Generator",
    # Sacral circuit gates → Generator
    5: "Generator", 14: "Generator", 29: "Generator", 59: "Generator",
    9: "Generator", 3: "Generator", 42: "Generator", 27: "Generator",
    # Logic (Understanding) circuit → Projector
    4: "Projector", 17: "Projector", 7: "Projector", 31: "Projector",
    63: "Projector", 64: "Projector", 11: "Projector", 56: "Projector",
    62: "Projector", 16: "Projector", 48: "Projector", 18: "Projector",
    # Abstract (Sensing) circuit → Generator
    13: "Generator", 33: "Generator", 30: "Generator", 55: "Generator",
    49: "Generator", 19: "Generator", 2: "Generator", 1: "Generator",
    8: "Projector", 23: "Projector",
    # Knowing (Individual) circuit → Projector/MG
    43: "Projector", 24: "Projector", 61: "Projector", 60: "Projector",
    41: "Generator", 39: "Generator", 38: "Manifesting Generator",
    # Throat / G-center bridges
    12: "Manifesting Generator", 22: "Manifesting Generator",
    35: "Manifesting Generator", 45: "Projector",
    # Root / Spleen
    53: "Generator", 60: "Generator", 52: "Generator", 58: "Generator",
    54: "Generator", 38: "Manifesting Generator", 28: "Projector",
    32: "Projector", 50: "Projector", 44: "Projector",
    57: "Manifestor", 6: "Generator",
    46: "Projector", 47: "Projector", 64: "Projector",
    # G / Identity center
    15: "Projector", 46: "Projector", 25: "Manifestor",
    10: "Manifestor", 7: "Projector", 1: "Generator",
    13: "Generator", 2: "Generator",
    # Reflector — assigned to a small set of gates
    36: "Reflector", 26: "Reflector",
}

_HD_TYPE_PROFILES: dict[str, tuple[str, str, str]] = {
    "Manifestor": (
        "The Manifestor",
        "You are here to initiate — to act on inspiration without waiting for permission. "
        "You have a rare, independent energy that can set things in motion for others. "
        "Your gift is impact. Your strategy: inform before you act.",
        "Informing those around you before major moves removes resistance and keeps your energy flowing freely.",
    ),
    "Generator": (
        "The Generator",
        "You are the life force of the world — a sustainable, magnetic energy that builds when engaged with the right work. "
        "Your power is in your response: when something truly lights you up, your energy is unstoppable. "
        "Your gift is mastery. Your strategy: wait to respond.",
        "Trust your gut response — that deep 'uh-huh' or 'uh-uh' — rather than initiating from the mind.",
    ),
    "Manifesting Generator": (
        "The Manifesting Generator",
        "You are a multi-passionate force of nature — fast, efficient, and built to do multiple things at once. "
        "You can initiate AND sustain, but only what genuinely lights you up. "
        "Your gift is speed and versatility. Your strategy: wait to respond, then inform.",
        "Honour your need to pivot — skipping steps that don't excite you isn't laziness, it's efficiency.",
    ),
    "Projector": (
        "The Projector",
        "You are here to guide — to see into systems and people with rare clarity and wisdom. "
        "You are not here to work like everyone else; you are here to direct and optimise. "
        "Your gift is insight. Your strategy: wait for the invitation.",
        "When you're invited and recognised, your guidance lands with transformative force. The right doors open to you.",
    ),
    "Reflector": (
        "The Reflector",
        "You are a mirror for the world — a rare being who reflects back the health and energy of your environment. "
        "You are deeply influenced by those around you and by the lunar cycle. "
        "Your gift is wisdom and clarity for others. Your strategy: wait a lunar cycle before major decisions.",
        "The right environment is everything for you — surrounding yourself with high-vibe people and places transforms your experience.",
    ),
}


def human_design_type(sun_degree: float) -> dict:
    """
    Determine simplified Human Design type from Sun's tropical degree (0–360).
    Returns type name and profile.
    """
    # Find which gate the Sun is in
    gate_index = int(sun_degree / 5.625) % 64
    gate = _RAVE_WHEEL[gate_index]
    line = int((sun_degree % 5.625) / 0.9375) + 1  # 1–6

    # Look up type tendency from gate map (default to Generator if not mapped)
    hd_type = _GATE_TYPE_MAP.get(gate, "Generator")
    title, description, strategy = _HD_TYPE_PROFILES[hd_type]

    return {
        "type": hd_type,
        "title": title,
        "description": description,
        "strategy": strategy,
        "sun_gate": gate,
        "sun_line": line,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CHAKRA / ENERGY PROFILE
# ─────────────────────────────────────────────────────────────────────────────

_LIFE_PATH_CHAKRA: dict[int, tuple[str, str]] = {
    1:  ("Solar Plexus",   "self-confidence, personal power, and the courage to lead"),
    2:  ("Heart",          "love, empathy, connection, and the giving and receiving of care"),
    3:  ("Throat",         "authentic expression, creativity, and the voice that wants to be heard"),
    4:  ("Root",           "stability, groundedness, and the safety to build and commit"),
    5:  ("Sacral",         "life force, pleasure, creativity, and the energy to experience fully"),
    6:  ("Heart",          "unconditional love, nurturing, and the harmony you carry for others"),
    7:  ("Crown",          "spiritual connection, higher wisdom, and the knowing beyond knowing"),
    8:  ("Root + Solar Plexus", "material power, ambition grounded in security"),
    9:  ("Heart + Crown",  "universal compassion, wisdom, and the wisdom born from a full life"),
    11: ("Third Eye",      "elevated intuition, visionary perception, and spiritual intelligence"),
    22: ("Root + Crown",   "the master builder's balance — visionary ideals grounded in reality"),
    33: ("Heart + Crown",  "the master healer's love — unconditional care and spiritual guidance"),
}

_ELEMENT_CHAKRA_QUALITY: dict[str, str] = {
    "Fire":  "Your energy is inherently activating — you ignite rooms, spark ideas, and move others into action.",
    "Earth": "Your energy is grounding and stabilising — you bring calm, reliability, and a sense of safety to those around you.",
    "Air":   "Your energy is mentally alive — you connect ideas, people, and possibilities with ease and intelligence.",
    "Water": "Your energy is deeply empathic and flowing — you sense what others feel before they say it.",
}

_SIGN_ELEMENTS: dict[str, str] = {
    "Aries": "Fire", "Leo": "Fire", "Sagittarius": "Fire",
    "Taurus": "Earth", "Virgo": "Earth", "Capricorn": "Earth",
    "Gemini": "Air", "Libra": "Air", "Aquarius": "Air",
    "Cancer": "Water", "Scorpio": "Water", "Pisces": "Water",
}


def chakra_energy_profile(life_path: int, sun_sign: str, moon_sign: str) -> dict:
    """
    Derive chakra/energy profile from Life Path number and key signs.
    """
    chakra_name, chakra_theme = _LIFE_PATH_CHAKRA.get(life_path, ("Heart", "love and connection"))
    sun_element  = _SIGN_ELEMENTS.get(sun_sign, "")
    moon_element = _SIGN_ELEMENTS.get(moon_sign, "")
    sun_quality  = _ELEMENT_CHAKRA_QUALITY.get(sun_element, "")
    moon_quality = _ELEMENT_CHAKRA_QUALITY.get(moon_element, "")

    return {
        "primary_chakra": chakra_name,
        "chakra_theme": chakra_theme,
        "sun_element": sun_element,
        "moon_element": moon_element,
        "sun_energy_quality": sun_quality,
        "moon_energy_quality": moon_quality,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SYNTHESIS — Build multi-framework summary for AI prompt injection
# ─────────────────────────────────────────────────────────────────────────────

def build_frameworks_summary(
    name: str,
    birth_date: str,
    chart_data: dict,
) -> str:
    """
    Compute all frameworks and return a formatted text block
    ready to be injected into AI prompts.

    Args:
        name:        User's full name
        birth_date:  Birth date string "YYYY-MM-DD"
        chart_data:  Chart dict from astrology.calculate_chart()
    """
    if not name or not birth_date or not chart_data:
        return ""

    try:
        # ── Numerology ─────────────────────────────────────────
        lp  = life_path_number(birth_date)
        exp = expression_number(name)
        su  = soul_urge_number(name)
        per = personality_number(name)

        lp_title,  lp_theme  = _LIFE_PATH_PROFILES.get(lp,  ("The Seeker", "growth and self-discovery"))
        exp_theme  = _EXPRESSION_THEMES.get(exp, "to express your unique gifts in service to others")
        su_theme   = _SOUL_URGE_THEMES.get(su,  "to find meaning and purpose in all you do")

        # ── Human Design ───────────────────────────────────────
        sun_degree = chart_data.get("sun_degree", 0.0)
        hd = human_design_type(sun_degree)

        # ── Chakra / Energy ────────────────────────────────────
        sun_sign  = chart_data.get("sun_sign", "")
        moon_sign = chart_data.get("moon_sign", "")
        chakra    = chakra_energy_profile(lp, sun_sign, moon_sign)

        lines = [
            "\n\n---\nMULTI-FRAMEWORK PERSONAL PROFILE:",
            "",
            "NUMEROLOGY:",
            f"Life Path {lp} — {lp_title}: their core life theme is {lp_theme}.",
            f"Expression Number {exp}: their outer purpose and direction is {exp_theme}.",
            f"Soul Urge Number {su}: {su_theme}.",
            f"Personality Number {per}: this shapes how the world first perceives them before they open up.",
            "",
            "HUMAN DESIGN (simplified gate-based assessment):",
            f"Type: {hd['type']} — {hd['title']}",
            hd['description'],
            f"Their strategy for alignment: {hd['strategy']}",
            f"Sun Gate {hd['sun_gate']}, Line {hd['sun_line']}.",
            "",
            "ENERGY / CHAKRA PROFILE:",
            f"Primary energy centre: {chakra['primary_chakra']} — themes of {chakra['chakra_theme']}.",
        ]

        if chakra['sun_energy_quality']:
            lines.append(f"Sun in {sun_sign} ({chakra['sun_element']} element): {chakra['sun_energy_quality']}")
        if chakra['moon_energy_quality'] and moon_sign != sun_sign:
            lines.append(f"Moon in {moon_sign} ({chakra['moon_element']} element): {chakra['moon_energy_quality']}")

        lines.append("")
        lines.append(
            "Use these frameworks to add depth and specificity to the reading. "
            "Weave the numerology, Human Design, and energy insights naturally into your prose — "
            "do not list them as separate sections. Let them enrich and validate what you see in the birth chart."
        )

        return "\n".join(lines)

    except Exception:
        return ""
