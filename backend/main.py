import os
import logging
from contextlib import asynccontextmanager
from datetime import date as _date_cls
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text
from apscheduler.schedulers.background import BackgroundScheduler
from .database import engine, Base, SessionLocal
from .routers import users, charts, payments, compatibility, admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def _run_migrations():
    """Add any missing columns to existing tables (safe to run repeatedly)."""
    migrations = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS reading_focus VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS life_context TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS life_event VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_superuser BOOLEAN DEFAULT FALSE",
        # Optional demographics for personalised AI readings
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS gender VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS marital_status VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS occupation VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS job_type VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS education_level VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS current_location VARCHAR",
        # Coordinates (added in previous release)
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_lat FLOAT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_lon FLOAT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_timezone VARCHAR",
        # Wellness profile — personal development onboarding questionnaire
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS wellness_goal VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS life_phase VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS primary_intention TEXT",
        # Living profile system — sensitive flags, profile summary, progressive profiling
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS sensitive_flags JSONB",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_summary TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_updated_at TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS profiling_stage INTEGER DEFAULT 0",
        # Engagement / streak tracking
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS current_streak INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS longest_streak INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active_date VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS total_active_days INTEGER DEFAULT 0",
        # Daily experience — intention column on horoscopes
        "ALTER TABLE daily_horoscopes ADD COLUMN IF NOT EXISTS intention TEXT",
        # Payment / subscription columns (not in original migrations)
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS free_uses INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_paid BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status VARCHAR DEFAULT 'free'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS paddle_subscription_id VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ",
        # Birth charts — full reading added after initial schema
        "ALTER TABLE birth_charts ADD COLUMN IF NOT EXISTS full_reading TEXT",
        # Compatibility reports — person2_sun_sign added after initial schema
        "ALTER TABLE compatibility_reports ADD COLUMN IF NOT EXISTS person2_sun_sign VARCHAR",
        # Conversion funnel — trial uses for new free users
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_uses INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_plan VARCHAR DEFAULT 'free'",
        # IP abuse prevention — registrations table
        """CREATE TABLE IF NOT EXISTS registration_ips (
            id SERIAL PRIMARY KEY,
            ip_address VARCHAR NOT NULL,
            user_id INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_registration_ips_ip_address ON registration_ips (ip_address)",
        # Password reset tokens
        """CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            token VARCHAR NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            used BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_token ON password_reset_tokens (token)",
        "CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user_id ON password_reset_tokens (user_id)",
        # Rename Paddle column to PayPal (column was mistakenly named after Paddle)
        "ALTER TABLE users RENAME COLUMN paddle_subscription_id TO paypal_subscription_id",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception as e:
                logger.warning(f"Migration skipped ({sql[:50]}…): {e}")


def _seed_superuser():
    """Create the admin superuser account if it doesn't exist."""
    from .auth import hash_password
    from . import models

    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "p.cooma@gmail.com")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "www.123@lk")
    ADMIN_NAME = os.getenv("ADMIN_NAME", "Admin")

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == ADMIN_EMAIL).first()
        if user:
            # Ensure existing account has superuser + paid flags
            if not user.is_superuser or not user.is_paid:
                user.is_superuser = True
                user.is_paid = True
                user.subscription_status = "active"
                db.commit()
                logger.info("Superuser flags updated for existing admin account")
        else:
            user = models.User(
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                name=ADMIN_NAME,
                is_superuser=True,
                is_paid=True,
                subscription_status="active",
            )
            db.add(user)
            db.commit()
            logger.info("Superuser account created")
    except Exception as e:
        logger.error(f"Superuser seed failed: {e}")
    finally:
        db.close()


def _send_daily_horoscope_emails():
    """Send today's horoscope email to all paid users who haven't received it yet."""
    from . import models as _models
    from .astrology import calculate_chart
    from .claude_ai import generate_daily_horoscope
    from .email_service import send_daily_horoscope_email

    today_str = _date_cls.today().isoformat()
    date_label = _date_cls.today().strftime("%A, %B %-d, %Y")

    db = SessionLocal()
    try:
        paid_users = db.query(_models.User).filter(
            _models.User.is_paid == True,  # noqa: E712
            _models.User.birth_date.isnot(None),
        ).all()

        logger.info("Daily email job: %d paid users to process", len(paid_users))

        for user in paid_users:
            try:
                # Check if today's horoscope email already sent
                horoscope_record = db.query(_models.DailyHoroscope).filter(
                    _models.DailyHoroscope.user_id == user.id,
                    _models.DailyHoroscope.date == today_str,
                ).first()

                if horoscope_record and horoscope_record.email_sent:
                    continue  # already sent

                # Get or generate horoscope
                if not horoscope_record:
                    stored_chart = db.query(_models.BirthChart).filter(
                        _models.BirthChart.user_id == user.id
                    ).first()
                    chart_data = (
                        stored_chart.chart_data if stored_chart and stored_chart.chart_data
                        else calculate_chart(
                            user.name, user.birth_date, user.birth_time,
                            user.birth_lat, user.birth_lon, user.birth_timezone,
                        )
                    )
                    content, intention = generate_daily_horoscope(
                        chart_data, _date_cls.today(),
                        wellness_goal=user.wellness_goal,
                        life_phase=user.life_phase,
                        primary_intention=user.primary_intention,
                        reading_focus=user.reading_focus,
                        sensitive_flags=user.sensitive_flags,
                        profile_summary=user.profile_summary,
                    )
                    horoscope_record = _models.DailyHoroscope(
                        user_id=user.id,
                        date=today_str,
                        content=content,
                        intention=intention or None,
                    )
                    db.add(horoscope_record)
                    db.commit()
                    db.refresh(horoscope_record)

                ok = send_daily_horoscope_email(
                    to_email=user.email,
                    name=user.name,
                    sun_sign=user.sun_sign or "Unknown",
                    horoscope=horoscope_record.content,
                    intention=horoscope_record.intention,
                    date_str=date_label,
                )
                if ok:
                    horoscope_record.email_sent = True
                    db.commit()

            except Exception as exc:
                logger.error("Daily email failed for user %s: %s", user.id, exc)
                db.rollback()

    except Exception as exc:
        logger.error("Daily email job error: %s", exc)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Warn if insecure defaults are still in use
    if not os.getenv("SECRET_KEY"):
        logger.warning("SECRET_KEY env var not set — using insecure default. Set this in Railway!")
    if not os.getenv("ADMIN_PASSWORD"):
        logger.warning("ADMIN_PASSWORD env var not set — using default credentials. Set this in Railway!")
    # Create all database tables on startup
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ready")
    # Add any missing columns to existing tables
    _run_migrations()
    logger.info("Migrations applied")
    # Ensure admin superuser exists
    _seed_superuser()
    logger.info("Superuser seeded")

    # Start the daily horoscope email scheduler (6 AM UTC every day)
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(_send_daily_horoscope_emails, "cron", hour=6, minute=0)
    scheduler.start()
    logger.info("Daily email scheduler started")

    yield

    scheduler.shutdown(wait=False)
    logger.info("Scheduler shut down")


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Set long-lived cache headers on static assets so browsers don't re-download them."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=604800"  # 7 days
        return response


app = FastAPI(
    title="Zodovia API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan
)

app.add_middleware(CacheControlMiddleware)

# API routes
app.include_router(users.router)
app.include_router(charts.router)
app.include_router(payments.router)
app.include_router(compatibility.router)
app.include_router(admin.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "zodovia"}


@app.get("/api/config")
def get_config():
    return {"google_maps_api_key": os.getenv("GOOGLE_MAPS_API_KEY", "")}


# Serve frontend static assets (CSS, JS)
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
static_dir = os.path.join(frontend_dir, "static")

if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    filepath = os.path.join(frontend_dir, "robots.txt")
    return FileResponse(filepath, media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml():
    filepath = os.path.join(frontend_dir, "sitemap.xml")
    return FileResponse(filepath, media_type="application/xml")


def _html_response(filepath: str) -> Response:
    return FileResponse(
        filepath,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
    )


# Catch-all: serve HTML pages from frontend/
@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    clean_path = full_path.strip("/")

    # Serve any file that physically exists in the frontend directory (e.g. verification files)
    direct_path = os.path.join(frontend_dir, clean_path)
    if os.path.isfile(direct_path):
        return FileResponse(direct_path)

    # Map known routes to HTML files
    page_map = {
        "": "index.html",
        "chart": "chart.html",
        "dashboard": "dashboard.html",
        "compatibility": "compatibility.html",
        "admin": "admin.html",
        "pricing": "pricing.html",
        "terms": "terms.html",
        "privacy": "privacy.html",
        "refund": "refund.html",
        "forgot-password": "forgot-password.html",
        "reset-password": "reset-password.html",
    }
    filename = page_map.get(clean_path, "index.html")
    filepath = os.path.join(frontend_dir, filename)

    if os.path.isfile(filepath):
        return _html_response(filepath)

    # Default to index for unknown paths (SPA-style fallback)
    index_path = os.path.join(frontend_dir, "index.html")
    return _html_response(index_path)
