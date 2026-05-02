import os
import threading
from datetime import datetime, timedelta, date as _date_cls
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .database import get_db
from . import models

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

FREE_LIMIT = 10   # hard block after this many compatibility uses
FREE_NUDGE_AT = 5  # show upgrade prompt from this point
TRIAL_LIMIT = 5   # paid-feature trial accesses granted to new free users

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> models.User:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_paid_user(current_user: models.User = Depends(get_current_user)) -> models.User:
    if not current_user.is_paid and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature requires a paid subscription"
        )
    return current_user


def get_paid_or_trial_user(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Allow paid users, superusers, and free users still within their trial allowance."""
    if current_user.is_paid or current_user.is_superuser:
        return current_user
    if (current_user.trial_uses or 0) < TRIAL_LIMIT:
        return current_user
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail="trial_exhausted"
    )


def increment_trial_use(user: models.User, db: Session) -> int:
    """Increment trial use counter for free users. Returns updated count. No-op for paid users."""
    if user.is_paid or user.is_superuser:
        return 0
    if (user.trial_uses or 0) < TRIAL_LIMIT:
        user.trial_uses = (user.trial_uses or 0) + 1
        db.commit()
    return user.trial_uses


def check_free_limit(user: models.User) -> None:
    """Validate free use limit without incrementing. Raises 402 if limit reached."""
    if user.is_paid or user.is_superuser:
        return
    if user.free_uses >= FREE_LIMIT:
        raise HTTPException(status_code=402, detail="free_limit_reached")


def increment_free_use(user: models.User, db: Session) -> int:
    """Increment the free use counter. Call AFTER successful generation."""
    if user.is_paid or user.is_superuser:
        return 0
    user.free_uses += 1
    db.commit()
    return user.free_uses


def check_free_use(user: models.User, db: Session) -> int:
    """
    For free users: increment the use counter and enforce the limit.
    Raises 402 if the free limit is reached.
    Returns the updated free_uses count (0 for paid users).
    """
    check_free_limit(user)
    return increment_free_use(user, db)


# ── Per-user daily AI rate limiter ────────────────────────────────────────────
# Protects against runaway cost from a single user spamming expensive Opus calls.

_AI_DAILY_ASK_STARS = 30   # ask-stars requests per user per day
_AI_DAILY_COMPAT    = 15   # compatibility requests per user per day

_ai_rate_lock  = threading.Lock()
_ai_rate_store: dict[int, dict] = {}  # user_id → {"date": "YYYY-MM-DD", "ask_stars": n, "compat": n}


def check_ai_rate_limit(user_id: int, feature: str) -> None:
    """Enforce per-user daily limits on expensive Opus AI features. Raises 429 if exceeded."""
    today = _date_cls.today().isoformat()
    limit = _AI_DAILY_ASK_STARS if feature == "ask_stars" else _AI_DAILY_COMPAT

    with _ai_rate_lock:
        entry = _ai_rate_store.get(user_id)
        if not entry or entry.get("date") != today:
            _ai_rate_store[user_id] = {"date": today, "ask_stars": 0, "compat": 0}
            entry = _ai_rate_store[user_id]

        if entry.get(feature, 0) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Daily limit reached for this feature. Please try again tomorrow.",
            )
        entry[feature] = entry.get(feature, 0) + 1
