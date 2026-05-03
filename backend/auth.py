import os
import threading
from datetime import datetime, timedelta, date as _date_cls
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from . import gas_client
from .gas_client import UserRecord

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production")
ALGORITHM  = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

FREE_LIMIT   = 10
FREE_NUDGE_AT = 5
TRIAL_LIMIT  = 5

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security    = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: int) -> str:
    expire  = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserRecord:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = await gas_client.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_paid_user(current_user: UserRecord = Depends(get_current_user)) -> UserRecord:
    if not current_user.is_paid and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="This feature requires a paid subscription")
    return current_user


async def get_paid_or_trial_user(
    current_user: UserRecord = Depends(get_current_user),
) -> UserRecord:
    if current_user.is_paid or current_user.is_superuser:
        return current_user
    if (current_user.trial_uses or 0) < TRIAL_LIMIT:
        return current_user
    raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED,
                        detail="trial_exhausted")


async def increment_trial_use(user: UserRecord) -> int:
    if user.is_paid or user.is_superuser:
        return 0
    if (user.trial_uses or 0) < TRIAL_LIMIT:
        new_count = (user.trial_uses or 0) + 1
        await gas_client.update_user(user.id, trial_uses=new_count)
        user.trial_uses = new_count
    return user.trial_uses or 0


def check_free_limit(user: UserRecord) -> None:
    if user.is_paid or user.is_superuser:
        return
    if (user.free_uses or 0) >= FREE_LIMIT:
        raise HTTPException(status_code=402, detail="free_limit_reached")


async def increment_free_use(user: UserRecord) -> int:
    if user.is_paid or user.is_superuser:
        return 0
    new_count = (user.free_uses or 0) + 1
    await gas_client.update_user(user.id, free_uses=new_count)
    user.free_uses = new_count
    return new_count


async def check_free_use(user: UserRecord) -> int:
    check_free_limit(user)
    return await increment_free_use(user)


# ── Per-user daily AI rate limiter ─────────────────────────────────
_AI_DAILY_ASK_STARS = 30
_AI_DAILY_COMPAT    = 15
_ai_rate_lock  = threading.Lock()
_ai_rate_store: dict[int, dict] = {}


def check_ai_rate_limit(user_id: int, feature: str) -> None:
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
