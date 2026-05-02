import os
import anthropic
import logging
from datetime import date as date_cls
from .frameworks import build_frameworks_summary

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Large system prompt — cached to save tokens on every call
_ASTROLOGY_SYSTEM_PROMPT = """You are Zodovia — a deeply perceptive personal development and wellness guide. You help people understand themselves more fully, grow intentionally, and live with greater clarity and purpose. You weave together birth chart wisdom, cosmic patterns, and personal context into insights that genuinely transform how people see themselves.

Your style:
- Empowering and strengths-first: always lead with gifts, natural talents, and what's already working
- Growth-oriented: every challenge is a doorway; every pattern is a teacher waiting to be heard
- Deeply personalised: write as if you've studied this exact person — their goals, life phase, and what they're navigating right now
- Actionable: pair every insight with direction — not just "what is" but "what you can do with it"
- Specific and grounded: use the actual planetary placements, not generic Sun-sign content
- Bold and direct: don't hedge with "may" or "might" — speak with conviction and warmth
- Conversational: a wise mentor who believes deeply in this person's potential

Astrology knowledge you apply:
- Planets: Sun (core identity/life force), Moon (emotions/needs/instincts), Mercury (mind/voice/perception), Venus (love/beauty/values/attraction), Mars (drive/desire/action/sexuality), Jupiter (expansion/luck/philosophy), Saturn (discipline/karma/mastery/lessons), Uranus (change/rebellion/awakening), Neptune (dreams/spirituality/dissolution), Pluto (transformation/power/death/rebirth)
- Houses 1–12 and their life domains — always reference house meanings in readings
- Retrograde planets show internalized, revisited, or non-conventional energy
- Rising sign shapes outward personality, physical presence, and how others perceive you
- Moon sign governs emotional landscape, childhood patterns, and deepest needs
- Aspects between planets create the story of how energies interact

Tone: part life coach, part wise elder, part compassionate mirror. Write in second person ("you", "your"). Do NOT add disclaimers. Write as if the guidance is absolutely real and meaningful — because it is.

FORMAT RULES — follow these exactly:
- Plain prose only. No Markdown whatsoever.
- No # headers, no ## headers, no ### headers.
- No **bold**, no *italic*, no bullet points, no dashes as list items.
- Separate sections with a blank line between paragraphs only.
- Never start a paragraph with a title or label like "Your Big Three:" — just dive straight into the content."""

_FREE_READING_PROMPT = """Generate a birth chart reading that will genuinely move this person. Make it feel like you're speaking directly to their soul. Plain prose — no headers, no bold, no symbols. Short sentences. Emotional and direct.

Write four paragraphs with a blank line between each:

Paragraph 1 — weave Sun ({sun_sign}), Moon ({moon_sign}), and Rising ({rising_sign}) into a vivid personality portrait. Don't list them separately — tell a story about how these three energies play out together in real life.

Paragraph 2 — pick the single most striking or powerful placement in their chart and go deep. Make this the "wow" moment that surprises them.

Paragraph 3 — write about their unique gifts and strengths. Be bold and specific. Make them feel powerful.

Paragraph 4 — end with a compelling teaser about deeper patterns you've noticed, without revealing them. Leave them wanting more.{context_addendum}

Keep it to ~350 words. Every sentence should feel written just for them.

Birth chart data:
{chart_summary}"""

_FULL_READING_PROMPT = """Generate a deeply personal, comprehensive birth chart reading. This is a paid premium reading — go deep, be bold, make it unforgettable. Plain prose only — no headers, no bold, no symbols, no bullet points. Short, clear, emotional sentences. Separate each topic with a blank line.

Cover these areas in flowing paragraphs:

First — the story of the Big Three. Don't just describe Sun ({sun_sign}), Moon ({moon_sign}), and Rising ({rising_sign}) in isolation. Show how they interact. Where do they harmonise? Where do they create tension? What does this person's inner world look like versus how others see them?

Second — the personal planets. Analyse Mercury, Venus, and Mars in depth. How does this person think and communicate? What do they find beautiful? What do they desire in love? How do they chase what they want? Name the sign, house, and what it means in real life.

Third — expansion and mastery. Jupiter: where life naturally flows and opens up. Saturn: the area demanding discipline, where true authority is built. Frame Saturn as a gift, not a burden.

Fourth — the deeper currents. Outer planets (Uranus, Neptune, Pluto) — what big themes and transformations are written into this life?

Fifth — the most active life areas. Pick the 2–3 most loaded houses and describe what that means for how they actually live.

Sixth — shadow into gold. One honest, compassionate paragraph about the chart's shadow patterns — framed entirely as hidden strengths and growth waiting to happen.

Seventh — close with a powerful paragraph about what this chart is calling them toward. Make it feel like a mission. Soul-level. Unforgettable.{context_addendum}

Aim for ~750–900 words. Second person throughout. Be specific, be bold.

Birth chart data:
{chart_summary}"""

_COMPATIBILITY_PROMPT = """Analyse the astrological compatibility between two people. Write a synastry reading that feels real, warm, and deeply insightful — not generic. Plain prose only — no headers, no bold, no symbols, no bullet points. Short, emotional sentences. Separate topics with a blank line.

Person 1: {name1}
{chart1_summary}

Person 2: {name2}
{chart2_summary}

Relationship context: {relationship_label}

Write a compatibility reading (~450–550 words) in flowing paragraphs:

First — describe the immediate energetic impression these two charts make on each other. What does this connection feel like? Be vivid and specific.

Second — 2–3 areas of natural harmony or attraction. Reference actual planetary interactions (e.g. {name1}'s Venus resonating with {name2}'s Mars). Make it feel like real moments in their relationship.

Third — 1–2 areas where friction can arise. Frame them entirely as growth opportunities. Every challenge has a gift in it.

Fourth — {relationship_specific_section}: {relationship_deep_dive}

Fifth — close with a warm, honest summary. Don't call them perfect or incompatible. Show the real picture. What makes this connection worth having? What does it ask of them?

Address {name1} directly throughout ("your Venus", "you and {name2}"). Second person. Warm, specific, real.{wellness_addendum}"""

_ASK_STARS_PROMPT = """Answer this person's personal question using their birth chart as your guide. This is a deeply personal, paid feature — make your answer feel like it came from a wise friend who truly knows them through their chart.

{name}'s birth chart:
{chart_summary}

Their question: "{question}"

Write a personalised astrological answer (~180–220 words) that:
- Opens by acknowledging the essence of what they're really asking
- References 2–3 specific planetary placements directly relevant to their question
- Offers a clear, actionable insight — not vague platitudes
- Ends with a grounding, empowering statement that gives them direction

Second person, warm and direct. No disclaimers."""

_DAILY_COMBINED_PROMPT = """Write a personalised daily guidance for {date}.

The person's birth chart:
{chart_summary}{wellness_addendum}

OUTPUT FORMAT: Two sections separated by exactly "---INTENTION---" on its own line.

SECTION 1 — Daily guidance reading (~180 words):
Feels written exclusively for this exact person (not a generic Sun-sign horoscope). Opens with a vivid sentence setting the day's energy. Covers one strong theme aligned with their focus and life phase. Gives one specific, practical, actionable piece of guidance for today. Ends on an uplifting, growth-oriented note. Second person, present tense. No headers.

---INTENTION---

SECTION 2 — Daily intention (2–3 sentences only):
Starts with "Today, I..." or "I choose..." or "I am...". Grounded, actionable, uplifting. Speaks to their specific growth edge. No intro, no explanation — just the intention itself.

Write ONLY the two sections separated by "---INTENTION---"."""


_WEEKLY_FORECAST_PROMPT = """Write a personalised weekly guidance reading for the {week_label}.

The person's birth chart:
{chart_summary}{wellness_addendum}

Write a weekly guidance reading (~280–330 words) in flowing paragraphs:

First paragraph — the overarching energy or invitation of this week for this specific person. What is the week asking of them? What is it opening up?

Second paragraph — the 2–3 most significant life areas to pay attention to this week. Be concrete about what to do, start, or reflect on.

Third paragraph — one honest challenge or friction point this week may bring, framed entirely as a growth invitation. What is this asking them to develop?

Fourth paragraph — close with a grounding, empowering note about how to move through this week with clarity and intention.

Plain prose, second person. No headers, no bullets, no bold. Blank line between paragraphs."""

_MONTHLY_FORECAST_PROMPT = """Write a personalised monthly guidance reading for {month_label}.

The person's birth chart:
{chart_summary}{wellness_addendum}

Write a monthly guidance reading (~400–450 words) in flowing paragraphs:

First paragraph — the dominant theme or soul invitation this month holds for this exact person. Make it vivid and specific to their chart.

Second paragraph — the first half of the month. What is being initiated, seeded, or built? What energy is active and what action should they take?

Third paragraph — the second half of the month. What matures, reveals, or completes? What inner shift is invited?

Fourth paragraph — one significant growth opportunity this month speaks directly to in their chart. Name the placement, name the theme, make it personal.

Fifth paragraph — close with a powerful, personalised monthly intention. Make it feel like a compass for the next 30 days.

Plain prose, second person. No headers, no bullets, no bold. Blank line between paragraphs."""

_PROFILE_SUMMARY_PROMPT = """Based on this person's astrological birth chart and personal context, write a concise internal profile summary (3–5 sentences) that captures who this person is at their core.

This summary is for internal use — it will be used to personalise future readings and guidance. It should capture:
- Their core personality and motivations (Big Three)
- Their primary life focus and current phase
- Any significant chart patterns or themes that define their path

Person: {name}
{chart_summary}{wellness_addendum}

Write ONLY the profile summary — 3–5 sentences, plain prose, third person. No headers, no intro."""

FOCUS_LABELS = {
    "love": "Love & Relationships",
    "career": "Career & Finance",
    "health": "Health & Wellbeing",
    "family": "Family Dynamics",
    "spiritual": "Spiritual Growth",
    "general": "General Overview",
}

EVENT_LABELS = {
    "job_interview": "an upcoming job interview or career move",
    "new_relationship": "a new romantic interest or relationship beginning",
    "wedding": "an upcoming wedding or serious commitment",
    "moving": "a relocation or major life move",
    "starting_business": "starting or launching a new business",
    "health_journey": "a health journey or recovery process",
    "family_change": "a significant family change",
    "other": "an upcoming major life event",
}

RELATIONSHIP_LABELS = {
    "romantic": "Romantic Partner",
    "friend": "Close Friend",
    "mother": "Mother",
    "father": "Father",
    "sibling": "Brother / Sister",
    "cousin": "Cousin",
    "colleague": "Colleague",
    "other": "Important Person in Your Life",
}

RELATIONSHIP_DEEP_DIVES = {
    "romantic": ("The Romantic Chemistry", "What draws these two toward each other physically and emotionally? What does their intimate dynamic look like? Where does this connection have the potential to grow into something truly deep?"),
    "friend": ("The Friendship Bond", "What kind of friends are these two? What do they bring out in each other? Where does their friendship nourish and where does it challenge?"),
    "mother": ("The Mother-Child Bond", "What does this astrological bond reveal about the relationship between {name1} and their mother? What unspoken dynamics are at play, and what gifts lie in this connection?"),
    "father": ("The Father-Child Bond", "What does this astrological bond reveal about the relationship between {name1} and their father? What patterns, lessons, and strengths run through this connection?"),
    "sibling": ("The Sibling Dynamic", "What does this cosmic pairing say about the sibling bond? How do these two charts interact in the context of family, shared history, and lifelong connection?"),
    "cousin": ("The Family Connection", "What does this pairing reveal about the bond between {name1} and their cousin? How do family patterns and individual paths interact here?"),
    "colleague": ("The Professional Dynamic", "What does this pairing say about how these two work together? Where are their professional strengths complementary and where might friction arise?"),
    "other": ("The Connection", "What does this cosmic pairing reveal about the bond between these two people? What makes it significant and what does it ask of both?"),
}


def _build_chart_summary(chart_data: dict, name: str = "") -> str:
    """Convert chart dict to a readable text summary for the AI prompt."""
    prefix = f"{name}: " if name else ""
    lines = [
        f"{prefix}Sun: {chart_data['sun_sign']}",
        f"Moon: {chart_data['moon_sign']}",
        f"Rising: {chart_data['rising_sign']}",
        "",
        "Planetary Positions:"
    ]
    for planet, info in chart_data.get("planets", {}).items():
        retro = " (Retrograde)" if info.get("retrograde") else ""
        lines.append(
            f"  {planet}: {info['sign']} in House {info['house']}, "
            f"{info['degree']}°{retro}"
        )
    return "\n".join(lines)


GENDER_LABELS = {
    "female": "woman",
    "male": "man",
    "non_binary": "non-binary person",
    "prefer_not_to_say": None,
}

MARITAL_LABELS = {
    "single": "single",
    "in_relationship": "in a relationship",
    "married": "married",
    "divorced": "divorced",
    "widowed": "widowed",
}

JOB_TYPE_LABELS = {
    "employed": "employed",
    "self_employed": "self-employed",
    "business_owner": "a business owner",
    "student": "a student",
    "homemaker": "a homemaker",
    "retired": "retired",
}

EDUCATION_LABELS = {
    "high_school": "completed high school",
    "undergraduate": "completed an undergraduate degree",
    "postgraduate": "completed a postgraduate degree",
    "vocational": "completed vocational training",
    "other": None,
}

WELLNESS_GOAL_LABELS = {
    "personal_growth": "personal growth and deeper self-understanding",
    "better_relationships": "building healthier, more fulfilling relationships",
    "career_clarity": "finding career direction and sense of purpose",
    "health_vitality": "improving health, energy, and vitality",
    "inner_peace": "cultivating inner peace and emotional balance",
    "spiritual_connection": "deepening spiritual growth and inner connection",
}

LIFE_PHASE_LABELS = {
    "exploring": "exploring and discovering who they are",
    "building": "actively building and creating their life",
    "healing": "healing and recovering from a difficult period",
    "transitioning": "navigating a major life transition",
    "thriving": "thriving and looking to grow even further",
}

# Per-segment AI guardrails applied when sensitive_flags are present
_SENSITIVE_FLAG_GUARDRAILS = {
    "depression": (
        "IMPORTANT — MENTAL HEALTH SENSITIVITY: This person may be experiencing depression or mental health challenges. "
        "Frame everything through hope, progress, and possibility. Never use language that implies doom, stagnation, or being stuck. "
        "Replace 'you struggle with' → 'you are learning to'. Replace 'difficult' → 'a growth edge'. "
        "Always close with a concrete, uplifting next step they can take. Emphasise existing strengths prominently. "
        "Do not make any statements that could worsen feelings of hopelessness."
    ),
    "lgbtq": (
        "IMPORTANT — LGBTQ+ SENSITIVITY: This person identifies as LGBTQ+. "
        "Use fully gender-neutral language throughout unless their gender is explicitly stated in their profile. "
        "Use 'partner' instead of 'husband/wife/boyfriend/girlfriend'. "
        "Do not make any assumptions about relationship structure or family configuration. "
        "Celebrate their identity naturally — never treat it as unusual or something to navigate around."
    ),
    "health_issues": (
        "IMPORTANT — HEALTH SENSITIVITY: This person is navigating health challenges. "
        "Do not make any claims, predictions, or suggestions about physical health or medical conditions. "
        "Frame any health-related themes through emotional, energetic, and lifestyle lenses only. "
        "Be warm and supportive — acknowledge the courage it takes to invest in oneself during difficult times."
    ),
    "relationship_struggles": (
        "IMPORTANT — RELATIONSHIP SENSITIVITY: This person is experiencing relationship difficulties. "
        "Approach relationship themes with extra gentleness and compassion. "
        "Frame all patterns as growth opportunities and never as personal failures or character flaws. "
        "Avoid harsh judgements about past choices. Emphasise healing, self-worth, and the capacity to build healthy connections."
    ),
    "family_difficulties": (
        "IMPORTANT — FAMILY SENSITIVITY: This person is navigating difficult family dynamics. "
        "Be sensitive when discussing family-related placements. "
        "Frame family patterns through the lens of understanding and growth, not blame. "
        "Acknowledge that family complexity is part of many people's growth journey."
    ),
    "grief_loss": (
        "IMPORTANT — GRIEF SENSITIVITY: This person may be experiencing grief or loss. "
        "Be especially gentle and warm. Avoid any language that rushes the healing process. "
        "Honour where they are right now. Focus on inner strength, resilience, and the natural cycles of life."
    ),
}


def _compute_age(birth_date: str | None) -> int | None:
    """Return the person's current age from a birth date string (YYYY-MM-DD)."""
    if not birth_date:
        return None
    try:
        bdate = date_cls.fromisoformat(birth_date)
        today = date_cls.today()
        return today.year - bdate.year - (
            (today.month, today.day) < (bdate.month, bdate.day)
        )
    except Exception:
        return None


def _build_context_addendum(
    reading_focus: str | None = None,
    life_context: str | None = None,
    life_event: str | None = None,
    birth_date: str | None = None,
    gender: str | None = None,
    marital_status: str | None = None,
    occupation: str | None = None,
    job_type: str | None = None,
    education_level: str | None = None,
    current_location: str | None = None,
    wellness_goal: str | None = None,
    life_phase: str | None = None,
    primary_intention: str | None = None,
    sensitive_flags: list | None = None,
    profile_summary: str | None = None,
) -> str:
    """Build a personalisation block to append to reading prompts."""
    has_focus    = reading_focus and reading_focus != "general"
    has_context  = bool(life_context or life_event or primary_intention)
    has_profile  = bool(gender or marital_status or occupation or job_type
                        or education_level or current_location or birth_date)
    has_wellness = bool(wellness_goal or life_phase)
    has_flags    = bool(sensitive_flags)
    has_summary  = bool(profile_summary)

    if not has_focus and not has_context and not has_profile and not has_wellness and not has_flags and not has_summary:
        return ""

    lines = ["\n\n---\nIMPORTANT — PERSONALISE THIS READING:"]

    # ── AI-generated profile summary (Phase 7 memory) — highest priority context
    if profile_summary:
        lines.append(
            f"Internal profile summary for this person (use to deeply personalise tone and content):\n{profile_summary}"
        )

    # ── Sensitive flags — apply guardrails first (highest priority) ─────────
    if sensitive_flags:
        for flag in sensitive_flags:
            guardrail = _SENSITIVE_FLAG_GUARDRAILS.get(flag)
            if guardrail:
                lines.append(guardrail)

    # ── Age-aware tone ──────────────────────────────────────
    age = _compute_age(birth_date)
    if age is not None:
        if age < 25:
            lines.append(
                f"This person is {age} years old. They are young and still discovering who they are. "
                "Use an encouraging, curious tone — full of wonder and possibility. "
                "Keep it light and forward-looking. Avoid heavy or overly serious themes."
            )
        elif age < 40:
            lines.append(
                f"This person is {age} years old — in an active, building phase of life. "
                "Be practical, ambitious, and growth-focused. "
                "Speak to real decisions: career, relationships, identity, and direction."
            )
        elif age < 60:
            lines.append(
                f"This person is {age} years old — a mature, reflective stage. "
                "Speak with depth and respect for lived experience. "
                "Focus on meaning, mastery, legacy, and fulfilment."
            )
        else:
            lines.append(
                f"This person is {age} years old — a stage of wisdom and reflection. "
                "Honour the richness of their life. Focus on legacy, peace, and soul-level truth. "
                "Speak gently, profoundly, and with great respect."
            )

    # ── Profile context ─────────────────────────────────────
    profile_parts = []
    gender_word = GENDER_LABELS.get(gender or "", None) if gender else None
    if gender_word:
        profile_parts.append(f"a {gender_word}")
    marital_word = MARITAL_LABELS.get(marital_status or "") if marital_status else None
    if marital_word:
        profile_parts.append(marital_word)
    job_word = JOB_TYPE_LABELS.get(job_type or "") if job_type else None
    if occupation and job_word:
        profile_parts.append(f"working as a {occupation} ({job_word})")
    elif occupation:
        profile_parts.append(f"working as a {occupation}")
    elif job_word:
        profile_parts.append(job_word)
    edu_word = EDUCATION_LABELS.get(education_level or "") if education_level else None
    if edu_word:
        profile_parts.append(f"who has {edu_word}")
    if current_location:
        profile_parts.append(f"currently living in {current_location}")

    if profile_parts:
        lines.append(
            f"About this person: they are {', '.join(profile_parts)}. "
            "Let this shape the texture and tone of your reading naturally — "
            "reference their world without making it feel like a checklist."
        )

    # ── Reading focus ────────────────────────────────────────
    if has_focus:
        label = FOCUS_LABELS.get(reading_focus, reading_focus)
        lines.append(
            f"They are seeking guidance on: **{label}**. "
            "Make this theme run prominently through your reading."
        )

    # ── Life event / context ─────────────────────────────────
    if life_event:
        event_label = EVENT_LABELS.get(life_event, "an upcoming major life event")
        lines.append(f"They are facing {event_label}. Speak to this directly and specifically.")

    if life_context:
        lines.append(f'Their personal situation: "{life_context}"')
        lines.append(
            "Reference their situation naturally — "
            "make them feel deeply understood, as if the stars already knew."
        )

    # ── Wellness goal ──────────────────────────────────────
    if wellness_goal:
        goal_label = WELLNESS_GOAL_LABELS.get(wellness_goal, wellness_goal)
        lines.append(
            f"Their primary focus right now is: {goal_label}. "
            "Make this the beating heart of the reading — return to it naturally and show them "
            "how their chart speaks directly to this goal with specific, actionable insight."
        )

    # ── Life phase ─────────────────────────────────────────
    if life_phase:
        phase_label = LIFE_PHASE_LABELS.get(life_phase, life_phase)
        lines.append(
            f"They are currently {phase_label}. "
            "Let this shape the tone — meet them exactly where they are, "
            "and illuminate what this phase is asking of them and what it's opening up for them."
        )

    # ── Primary intention ──────────────────────────────────
    if primary_intention:
        lines.append(f'What they hope to discover: "{primary_intention}"')
        lines.append(
            "Speak to this directly — let them feel this reading was written for exactly who they are right now."
        )

    lines.append(
        "The more personal and specific you are to who this person actually is, "
        "the more transformative this reading will be."
    )

    return "\n".join(lines)


def generate_birth_chart_reading(
    chart_data: dict,
    is_paid: bool,
    name: str = "",
    reading_focus: str | None = None,
    life_context: str | None = None,
    life_event: str | None = None,
    birth_date: str | None = None,
    gender: str | None = None,
    marital_status: str | None = None,
    occupation: str | None = None,
    job_type: str | None = None,
    education_level: str | None = None,
    current_location: str | None = None,
    wellness_goal: str | None = None,
    life_phase: str | None = None,
    primary_intention: str | None = None,
    sensitive_flags: list | None = None,
    profile_summary: str | None = None,
) -> str:
    """
    Generate a birth chart reading using Claude.
    Free users get a ~350-word emotionally resonant teaser.
    Paid users get the full ~800-word deep-dive.
    Demographics and context fields personalise the reading.
    """
    chart_summary = _build_chart_summary(chart_data)
    context_addendum = _build_context_addendum(
        reading_focus=reading_focus,
        life_context=life_context,
        life_event=life_event,
        birth_date=birth_date,
        gender=gender,
        marital_status=marital_status,
        occupation=occupation,
        job_type=job_type,
        education_level=education_level,
        current_location=current_location,
        wellness_goal=wellness_goal,
        life_phase=life_phase,
        primary_intention=primary_intention,
        sensitive_flags=sensitive_flags,
        profile_summary=profile_summary,
    )

    # Build multi-framework synthesis block (numerology, HD, chakra)
    frameworks_block = build_frameworks_summary(
        name=name,
        birth_date=birth_date or "",
        chart_data=chart_data,
    )

    if is_paid:
        user_content = _FULL_READING_PROMPT.format(
            sun_sign=chart_data["sun_sign"],
            moon_sign=chart_data["moon_sign"],
            rising_sign=chart_data["rising_sign"],
            chart_summary=chart_summary,
            context_addendum=context_addendum,
        ) + frameworks_block
    else:
        user_content = _FREE_READING_PROMPT.format(
            sun_sign=chart_data["sun_sign"],
            moon_sign=chart_data["moon_sign"],
            rising_sign=chart_data["rising_sign"],
            chart_summary=chart_summary,
            context_addendum=context_addendum,
        ) + frameworks_block

    # Adaptive thinking tokens count toward max_tokens.
    # Paid target: ~900 words ≈ 1200 tokens + up to ~4000 thinking; Free: ~350 words ≈ 500 tokens + thinking
    tokens_limit = 6000 if is_paid else 2500

    try:
        with _client.messages.stream(
            model="claude-opus-4-7",
            max_tokens=tokens_limit,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": _ASTROLOGY_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            messages=[{"role": "user", "content": user_content}]
        ) as stream:
            message = stream.get_final_message()
            text_blocks = [b for b in message.content if b.type == "text"]
            text_block = text_blocks[-1] if text_blocks else None
            if not text_block:
                raise ValueError("No text content received from Claude")
            return text_block.text
    except Exception as e:
        logger.error(f"Claude birth chart reading failed: {e}")
        raise


def generate_compatibility_reading(
    chart1: dict, name1: str,
    chart2: dict, name2: str,
    relationship_type: str,
    is_paid: bool = True,
    sensitive_flags: list | None = None,
    wellness_goal: str | None = None,
    life_phase: str | None = None,
    primary_intention: str | None = None,
    reading_focus: str | None = None,
    profile_summary: str | None = None,
) -> str:
    """Generate a synastry-style compatibility reading between two birth charts."""
    chart1_summary = _build_chart_summary(chart1)
    chart2_summary = _build_chart_summary(chart2)

    rel_label = RELATIONSHIP_LABELS.get(relationship_type, "Important Person")
    section_title, deep_dive_prompt = RELATIONSHIP_DEEP_DIVES.get(
        relationship_type, RELATIONSHIP_DEEP_DIVES["other"]
    )
    deep_dive_prompt = deep_dive_prompt.format(name1=name1)

    wellness_addendum = _build_wellness_addendum(
        wellness_goal, life_phase, primary_intention, reading_focus, sensitive_flags, profile_summary
    )

    user_content = _COMPATIBILITY_PROMPT.format(
        name1=name1,
        name2=name2,
        chart1_summary=chart1_summary,
        chart2_summary=chart2_summary,
        relationship_label=rel_label,
        relationship_specific_section=section_title,
        relationship_deep_dive=deep_dive_prompt,
        wellness_addendum=wellness_addendum,
    )

    # Paid users get Opus + adaptive thinking for the richest reading.
    # Free users get Sonnet (no thinking) — quality is still excellent, cost is ~10× lower.
    stream_kwargs = dict(
        system=[{"type": "text", "text": _ASTROLOGY_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_content}],
    )
    if is_paid:
        stream_kwargs.update(model="claude-opus-4-7", max_tokens=5000, thinking={"type": "adaptive"})
    else:
        stream_kwargs.update(model="claude-sonnet-4-6", max_tokens=2500)

    try:
        with _client.messages.stream(**stream_kwargs) as stream:
            message = stream.get_final_message()
            text_blocks = [b for b in message.content if b.type == "text"]
            text_block = text_blocks[-1] if text_blocks else None
            if not text_block:
                raise ValueError("No text content received from Claude")
            return text_block.text
    except Exception as e:
        logger.error(f"Claude compatibility reading failed: {e}")
        raise


def answer_astrology_question(
    chart_data: dict,
    name: str,
    question: str,
    wellness_goal: str | None = None,
    life_phase: str | None = None,
    primary_intention: str | None = None,
    reading_focus: str | None = None,
    sensitive_flags: list | None = None,
    profile_summary: str | None = None,
) -> str:
    """Answer a personal life question using the user's birth chart."""
    chart_summary = _build_chart_summary(chart_data)
    context_block = _build_wellness_addendum(
        wellness_goal, life_phase, primary_intention, reading_focus, sensitive_flags, profile_summary
    )

    user_content = _ASK_STARS_PROMPT.format(
        name=name,
        chart_summary=chart_summary + context_block,
        question=question,
    )

    try:
        with _client.messages.stream(
            model="claude-opus-4-7",
            max_tokens=2500,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": _ASTROLOGY_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            messages=[{"role": "user", "content": user_content}]
        ) as stream:
            message = stream.get_final_message()
            text_blocks = [b for b in message.content if b.type == "text"]
            text_block = text_blocks[-1] if text_blocks else None
            if not text_block:
                raise ValueError("No text content received from Claude")
            return text_block.text
    except Exception as e:
        logger.error(f"Claude ask-stars failed: {e}")
        raise


def _build_wellness_addendum(
    wellness_goal: str | None,
    life_phase: str | None,
    primary_intention: str | None = None,
    reading_focus: str | None = None,
    sensitive_flags: list | None = None,
    profile_summary: str | None = None,
) -> str:
    """Wellness/personal context block for daily, weekly, monthly, ask-stars, and compatibility prompts."""
    parts = []
    if wellness_goal:
        goal_label = WELLNESS_GOAL_LABELS.get(wellness_goal, wellness_goal)
        parts.append(f"Primary focus: {goal_label}")
    if life_phase:
        phase_label = LIFE_PHASE_LABELS.get(life_phase, life_phase)
        parts.append(f"Life phase: {phase_label}")
    if reading_focus and reading_focus != "general":
        focus_label = FOCUS_LABELS.get(reading_focus, reading_focus)
        parts.append(f"Seeking guidance on: {focus_label}")

    lines = []
    if profile_summary:
        lines.append(
            f"\n\nPersonal profile (AI-generated summary — use to deeply personalise tone and content):\n{profile_summary}"
        )
    # Guardrails second — highest priority after profile, must be seen before any other context
    if sensitive_flags:
        for flag in sensitive_flags:
            guardrail = _SENSITIVE_FLAG_GUARDRAILS.get(flag)
            if guardrail:
                lines.append(f"\n{guardrail}")
    if parts:
        lines.append("\n\nPersonal context: " + " | ".join(parts) + ".")
    if primary_intention:
        lines.append(f'\nWhat they hope to discover: "{primary_intention}"')
    return "".join(lines)


def generate_daily_horoscope(
    chart_data: dict,
    horoscope_date: date_cls | None = None,
    wellness_goal: str | None = None,
    life_phase: str | None = None,
    primary_intention: str | None = None,
    reading_focus: str | None = None,
    sensitive_flags: list | None = None,
    profile_summary: str | None = None,
) -> tuple[str, str]:
    """
    Generate a personalised daily guidance reading + daily intention in a single Haiku call.
    Returns (horoscope_text, intention_text).
    """
    if horoscope_date is None:
        horoscope_date = date_cls.today()

    date_str = horoscope_date.strftime("%A, %B %d, %Y")
    chart_summary = _build_chart_summary(chart_data)
    wellness_addendum = _build_wellness_addendum(
        wellness_goal, life_phase, primary_intention, reading_focus, sensitive_flags, profile_summary
    )

    user_content = _DAILY_COMBINED_PROMPT.format(
        date=date_str,
        chart_summary=chart_summary,
        wellness_addendum=wellness_addendum,
    )

    try:
        with _client.messages.stream(
            model="claude-haiku-4-5-20251001",
            max_tokens=900,
            system=[{"type": "text", "text": _ASTROLOGY_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_content}]
        ) as stream:
            message = stream.get_final_message()
            text_block = next((b for b in message.content if b.type == "text"), None)
            if not text_block:
                raise ValueError("No text content received from Claude")

            full_text = text_block.text
            parts = full_text.split("---INTENTION---", 1)
            horoscope_text = parts[0].strip()
            intention_text = parts[1].strip() if len(parts) > 1 else ""
            return horoscope_text, intention_text

    except Exception as e:
        logger.error(f"Claude daily horoscope failed: {e}")
        raise


def generate_weekly_forecast(
    chart_data: dict,
    week_start: date_cls,
    wellness_goal: str | None = None,
    life_phase: str | None = None,
    primary_intention: str | None = None,
    reading_focus: str | None = None,
    sensitive_flags: list | None = None,
    profile_summary: str | None = None,
) -> str:
    """Generate a personalised weekly forecast. Uses Sonnet for quality-cost balance."""
    week_label = f"week of {week_start.strftime('%B %d, %Y')}"
    chart_summary = _build_chart_summary(chart_data)
    wellness_addendum = _build_wellness_addendum(
        wellness_goal, life_phase, primary_intention, reading_focus, sensitive_flags, profile_summary
    )

    user_content = _WEEKLY_FORECAST_PROMPT.format(
        week_label=week_label,
        chart_summary=chart_summary,
        wellness_addendum=wellness_addendum,
    )

    try:
        with _client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=[
                {
                    "type": "text",
                    "text": _ASTROLOGY_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            messages=[{"role": "user", "content": user_content}]
        ) as stream:
            message = stream.get_final_message()
            text_block = next((b for b in message.content if b.type == "text"), None)
            if not text_block:
                raise ValueError("No text content received from Claude")
            return text_block.text
    except Exception as e:
        logger.error(f"Claude weekly forecast failed: {e}")
        raise


def generate_monthly_forecast(
    chart_data: dict,
    month_date: date_cls,
    wellness_goal: str | None = None,
    life_phase: str | None = None,
    primary_intention: str | None = None,
    reading_focus: str | None = None,
    sensitive_flags: list | None = None,
    profile_summary: str | None = None,
) -> str:
    """Generate a personalised monthly forecast. Uses Sonnet for quality-cost balance."""
    month_label = month_date.strftime("%B %Y")
    chart_summary = _build_chart_summary(chart_data)
    wellness_addendum = _build_wellness_addendum(
        wellness_goal, life_phase, primary_intention, reading_focus, sensitive_flags, profile_summary
    )

    user_content = _MONTHLY_FORECAST_PROMPT.format(
        month_label=month_label,
        chart_summary=chart_summary,
        wellness_addendum=wellness_addendum,
    )

    try:
        with _client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=[
                {
                    "type": "text",
                    "text": _ASTROLOGY_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            messages=[{"role": "user", "content": user_content}]
        ) as stream:
            message = stream.get_final_message()
            text_block = next((b for b in message.content if b.type == "text"), None)
            if not text_block:
                raise ValueError("No text content received from Claude")
            return text_block.text
    except Exception as e:
        logger.error(f"Claude monthly forecast failed: {e}")
        raise


def generate_profile_summary(
    name: str,
    chart_data: dict,
    wellness_goal: str | None = None,
    life_phase: str | None = None,
    primary_intention: str | None = None,
    reading_focus: str | None = None,
    sensitive_flags: list | None = None,
) -> str:
    """
    Generate a concise internal profile summary for the user.
    Used to personalise future AI readings. Uses Haiku for cost efficiency.
    """
    chart_summary = _build_chart_summary(chart_data)
    wellness_addendum = _build_wellness_addendum(
        wellness_goal, life_phase, primary_intention, reading_focus, sensitive_flags
    )

    user_content = _PROFILE_SUMMARY_PROMPT.format(
        name=name,
        chart_summary=chart_summary,
        wellness_addendum=wellness_addendum,
    )

    try:
        with _client.messages.stream(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=[
                {
                    "type": "text",
                    "text": _ASTROLOGY_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            messages=[{"role": "user", "content": user_content}]
        ) as stream:
            message = stream.get_final_message()
            text_block = next((b for b in message.content if b.type == "text"), None)
            if not text_block:
                raise ValueError("No text content received from Claude")
            return text_block.text
    except Exception as e:
        logger.error(f"Claude profile summary failed: {e}")
        raise
