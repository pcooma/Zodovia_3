from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Float, JSON
from sqlalchemy.sql import func
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name = Column(String, nullable=False)

    # Birth data
    birth_date = Column(String)       # "1990-01-15"
    birth_time = Column(String)       # "14:30"
    birth_city = Column(String)
    birth_lat = Column(Float)
    birth_lon = Column(Float)
    birth_timezone = Column(String)   # "America/New_York"

    # Computed signs (cached after first calculation)
    sun_sign = Column(String)
    moon_sign = Column(String)
    rising_sign = Column(String)

    # Reading personalisation (optional, captured at birth-data submission)
    reading_focus = Column(String, nullable=True)   # "love", "career", "health", "family", "spiritual", "general"
    life_context = Column(Text, nullable=True)       # Free text: "I'm thinking about a career change"
    life_event = Column(String, nullable=True)       # "job_interview", "new_relationship", "wedding", etc.

    # Optional demographics — used to personalise AI readings
    gender = Column(String, nullable=True)           # "female" / "male" / "non_binary" / "prefer_not_to_say"
    marital_status = Column(String, nullable=True)   # "single" / "in_relationship" / "married" / "divorced" / "widowed"
    occupation = Column(String, nullable=True)       # Free text: "Software Engineer", "Teacher", "Student"
    job_type = Column(String, nullable=True)         # "employed" / "self_employed" / "business_owner" / "student" / "homemaker" / "retired"
    education_level = Column(String, nullable=True)  # "high_school" / "undergraduate" / "postgraduate" / "vocational" / "other"
    current_location = Column(String, nullable=True) # Where they live now (may differ from birth city)

    # Wellness profile — personal development onboarding questionnaire
    wellness_goal = Column(String, nullable=True)    # "personal_growth" / "better_relationships" / "career_clarity" / "health_vitality" / "inner_peace" / "spiritual_connection"
    life_phase = Column(String, nullable=True)        # "exploring" / "building" / "healing" / "transitioning" / "thriving"
    primary_intention = Column(Text, nullable=True)   # Free text: what they hope to discover or achieve

    # Sensitive user flags — self-identified, used to apply AI guardrails
    # Stored as JSON list, e.g. ["depression", "lgbtq", "health_issues", "relationship_struggles"]
    sensitive_flags = Column(JSON, nullable=True)

    # Living profile — AI-generated rolling summary (updated periodically)
    profile_summary = Column(Text, nullable=True)
    profile_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Progressive profiling — tracks how far along the user is in guided Q&A
    profiling_stage = Column(Integer, default=0)     # 0 = fresh, increments as questions are answered

    # Engagement / streak tracking
    current_streak = Column(Integer, default=0)      # consecutive days active
    longest_streak = Column(Integer, default=0)
    last_active_date = Column(String, nullable=True) # "YYYY-MM-DD"
    total_active_days = Column(Integer, default=0)

    # Admin
    is_superuser = Column(Boolean, default=False)

    # Free tier usage counter (compatibility checks)
    free_uses = Column(Integer, default=0)

    # Trial: how many paid-feature accesses the user has consumed
    trial_uses = Column(Integer, default=0)

    # Subscription
    is_paid = Column(Boolean, default=False)
    paypal_subscription_id = Column(String, nullable=True)
    subscription_status = Column(String, default="free")  # free / active / cancelled
    subscription_plan = Column(String, default="free")    # free / monthly / yearly

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)


class BirthChart(Base):
    __tablename__ = "birth_charts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    chart_data = Column(JSON)           # raw planetary positions from Kerykeion
    free_reading = Column(Text)         # Claude-generated basic reading
    full_reading = Column(Text)         # Claude-generated detailed reading (paid)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CompatibilityReport(Base):
    __tablename__ = "compatibility_reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    person2_name = Column(String, nullable=False)
    person2_birth_date = Column(String)
    person2_birth_time = Column(String)
    person2_birth_city = Column(String)
    person2_sun_sign = Column(String, nullable=True)
    relationship_type = Column(String, nullable=False)  # "romantic", "friend", "mother", "father", "sibling", "cousin", "colleague"
    report = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Forecast(Base):
    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    period_type = Column(String, nullable=False)  # "week" / "month"
    period_key = Column(String, nullable=False)    # "2026-W16" / "2026-04"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DailyHoroscope(Base):
    __tablename__ = "daily_horoscopes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    date = Column(String, nullable=False)         # "2024-01-15"
    content = Column(Text, nullable=False)        # Claude-generated personalized horoscope
    intention = Column(Text, nullable=True)       # Claude-generated daily intention/affirmation
    email_sent = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RegistrationIP(Base):
    """Records IP addresses used during registration to limit abuse."""
    __tablename__ = "registration_ips"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, index=True, nullable=False)
    user_id = Column(Integer, nullable=True)      # linked user (None if registration failed)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
