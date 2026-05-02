from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("name")
    @classmethod
    def name_max_length(cls, v: str) -> str:
        if len(v) > 100:
            raise ValueError("Name must be at most 100 characters")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class BirthDataSubmit(BaseModel):
    birth_date: str       # "1990-01-15"
    birth_time: str       # "14:30" — "12:00" if unknown
    birth_city: str       # "Colombo, Sri Lanka"
    name: Optional[str] = None

    @field_validator("birth_city")
    @classmethod
    def city_max_length(cls, v: str) -> str:
        if len(v) > 200:
            raise ValueError("Birth city must be at most 200 characters")
        return v
    # Exact coordinates (optional — skips geocoding when provided)
    birth_lat: Optional[float] = None
    birth_lon: Optional[float] = None

    @field_validator("birth_lat")
    @classmethod
    def birth_lat_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (-90.0 <= v <= 90.0):
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @field_validator("birth_lon")
    @classmethod
    def birth_lon_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (-180.0 <= v <= 180.0):
            raise ValueError("Longitude must be between -180 and 180")
        return v
    # Optional personalisation
    reading_focus: Optional[str] = None   # "love", "career", "health", "family", "spiritual", "general"
    life_context: Optional[str] = None    # Free text description of situation
    life_event: Optional[str] = None      # "job_interview", "new_relationship", "wedding", "moving", etc.
    # Optional demographics — for more personalised AI readings
    gender: Optional[str] = None                # "female" / "male" / "non_binary" / "prefer_not_to_say"
    marital_status: Optional[str] = None        # "single" / "in_relationship" / "married" / "divorced" / "widowed"
    occupation: Optional[str] = None            # Free text: "Teacher", "Engineer"
    job_type: Optional[str] = None              # "employed" / "self_employed" / "business_owner" / "student" / "homemaker" / "retired"
    education_level: Optional[str] = None       # "high_school" / "undergraduate" / "postgraduate" / "vocational" / "other"
    current_location: Optional[str] = None      # Where they live now
    # Wellness profile
    wellness_goal: Optional[str] = None         # "personal_growth" / "better_relationships" / "career_clarity" / "health_vitality" / "inner_peace" / "spiritual_connection"
    life_phase: Optional[str] = None            # "exploring" / "building" / "healing" / "transitioning" / "thriving"
    primary_intention: Optional[str] = None     # Free text: what they hope to discover
    # Sensitive user flags (self-identified)
    sensitive_flags: Optional[List[str]] = None  # e.g. ["depression", "lgbtq", "health_issues", "relationship_struggles"]

    @field_validator("life_context")
    @classmethod
    def life_context_max_length(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 2000:
            raise ValueError("Life context must be at most 2000 characters")
        return v

    @field_validator("primary_intention")
    @classmethod
    def primary_intention_max_length(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 400:
            raise ValueError("Primary intention must be at most 400 characters")
        return v

    @field_validator("occupation")
    @classmethod
    def occupation_max_length(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 100:
            raise ValueError("Occupation must be at most 100 characters")
        return v

    @field_validator("current_location")
    @classmethod
    def current_location_max_length(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 200:
            raise ValueError("Current location must be at most 200 characters")
        return v


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    sun_sign: Optional[str] = None
    moon_sign: Optional[str] = None
    rising_sign: Optional[str] = None
    birth_date: Optional[str] = None
    birth_time: Optional[str] = None
    birth_city: Optional[str] = None
    reading_focus: Optional[str] = None
    is_paid: Optional[bool] = False
    is_superuser: Optional[bool] = False
    subscription_status: Optional[str] = "free"
    subscription_plan: Optional[str] = "free"
    free_uses: Optional[int] = 0
    trial_uses: Optional[int] = 0
    # Demographics
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    occupation: Optional[str] = None
    job_type: Optional[str] = None
    education_level: Optional[str] = None
    current_location: Optional[str] = None
    # Wellness profile
    wellness_goal: Optional[str] = None
    life_phase: Optional[str] = None
    primary_intention: Optional[str] = None
    # Sensitive flags
    sensitive_flags: Optional[List[str]] = None
    profiling_stage: Optional[int] = 0
    # Engagement / streak tracking
    current_streak: Optional[int] = 0
    longest_streak: Optional[int] = 0
    total_active_days: Optional[int] = 0
    # Intelligence / memory
    profile_summary: Optional[str] = None

    class Config:
        from_attributes = True


class AdminUserSummary(BaseModel):
    id: int
    email: str
    name: str
    is_paid: Optional[bool] = False
    subscription_status: Optional[str] = "free"
    sun_sign: Optional[str] = None
    moon_sign: Optional[str] = None
    rising_sign: Optional[str] = None
    birth_city: Optional[str] = None
    birth_date: Optional[str] = None
    reading_focus: Optional[str] = None
    life_event: Optional[str] = None
    created_at: Optional[str] = None
    last_login: Optional[str] = None
    has_chart: bool = False
    has_full_reading: bool = False
    # Demographics
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    occupation: Optional[str] = None
    current_location: Optional[str] = None

    class Config:
        from_attributes = True


class AdminUserDetail(AdminUserSummary):
    life_context: Optional[str] = None
    free_reading: Optional[str] = None
    full_reading: Optional[str] = None
    job_type: Optional[str] = None
    education_level: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ChartResponse(BaseModel):
    sun_sign: str
    moon_sign: str
    rising_sign: str
    rising_degree: float = 0.0
    planets: dict
    free_reading: str
    is_paid: bool


class HoroscopeResponse(BaseModel):
    date: str
    content: str


class CompatibilityRequest(BaseModel):
    person2_name: str
    person2_birth_date: str   # "1990-01-15"
    person2_birth_time: str   # "14:30"
    person2_birth_city: str
    relationship_type: str    # "romantic", "friend", "mother", "father", "sibling", "cousin", "colleague"
    person2_birth_lat: Optional[float] = None
    person2_birth_lon: Optional[float] = None

    @field_validator("person2_birth_lat")
    @classmethod
    def person2_lat_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (-90.0 <= v <= 90.0):
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @field_validator("person2_birth_lon")
    @classmethod
    def person2_lon_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (-180.0 <= v <= 180.0):
            raise ValueError("Longitude must be between -180 and 180")
        return v

    @field_validator("person2_name")
    @classmethod
    def person2_name_max_length(cls, v: str) -> str:
        if len(v) > 100:
            raise ValueError("Name must be at most 100 characters")
        return v

    @field_validator("person2_birth_city")
    @classmethod
    def person2_city_max_length(cls, v: str) -> str:
        if len(v) > 200:
            raise ValueError("Birth city must be at most 200 characters")
        return v


class CompatibilityResponse(BaseModel):
    person2_name: str
    person2_sun_sign: str
    relationship_type: str
    report: str
    free_uses_remaining: Optional[int] = None  # None for paid users


class ForecastResponse(BaseModel):
    period_type: str    # "week" / "month"
    period_key: str     # "2026-W16" / "2026-04"
    content: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class AskStarsRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def question_length(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Question cannot be empty")
        if len(v) > 600:
            raise ValueError("Question must be at most 600 characters")
        return v


class AskStarsResponse(BaseModel):
    answer: str
    free_uses_remaining: Optional[int] = None  # None for paid users
