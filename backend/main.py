import asyncio
import os
import logging
from contextlib import asynccontextmanager
from datetime import date as _date_cls
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from .routers import users, charts, payments, compatibility, admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def _seed_superuser() -> None:
    from . import gas_client
    from .auth import hash_password

    ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL",    "p.cooma@gmail.com")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "www.123@lk")
    ADMIN_NAME     = os.getenv("ADMIN_NAME",     "Admin")

    try:
        user = await gas_client.get_user_by_email(ADMIN_EMAIL)
        if user:
            if not user.is_superuser or not user.is_paid:
                await gas_client.update_user(user.id,
                    is_superuser=True, is_paid=True, subscription_status="active")
                logger.info("Superuser flags updated")
        else:
            await gas_client.create_user(
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                name=ADMIN_NAME,
                is_superuser=True,
                is_paid=True,
                subscription_status="active",
            )
            logger.info("Superuser account created")
    except Exception as e:
        logger.error(f"Superuser seed failed: {e}")


def _send_daily_horoscope_emails() -> None:
    """Sync wrapper called by APScheduler (runs in a thread)."""
    asyncio.run(_send_daily_horoscope_emails_async())


async def _send_daily_horoscope_emails_async() -> None:
    from . import gas_client
    from .astrology import calculate_chart
    from .claude_ai import generate_daily_horoscope
    from .email_service import send_daily_horoscope_email

    today_str  = _date_cls.today().isoformat()
    date_label = _date_cls.today().strftime("%A, %B %-d, %Y")

    try:
        paid_users = await gas_client.get_paid_users_for_daily()
        logger.info("Daily email job: %d paid users", len(paid_users))

        for user in paid_users:
            try:
                horoscope = await gas_client.get_daily_horoscope(user.id, today_str)
                if horoscope and horoscope.email_sent:
                    continue

                if not horoscope:
                    stored_chart = await gas_client.get_chart(user.id)
                    chart_data = (
                        stored_chart.chart_data
                        if stored_chart and stored_chart.chart_data
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
                    horoscope = await gas_client.save_daily_horoscope(
                        user.id, today_str, content, intention=intention
                    )

                ok = send_daily_horoscope_email(
                    to_email=user.email,
                    name=user.name,
                    sun_sign=user.sun_sign or "Unknown",
                    horoscope=horoscope.content,
                    intention=horoscope.intention,
                    date_str=date_label,
                )
                if ok:
                    await gas_client.update_daily_horoscope(user.id, today_str, email_sent=True)

            except Exception as exc:
                logger.error("Daily email failed for user %s: %s", user.id, exc)

    except Exception as exc:
        logger.error("Daily email job error: %s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not os.getenv("SECRET_KEY"):
        logger.warning("SECRET_KEY not set — using insecure default")
    if not os.getenv("GAS_URL"):
        logger.warning("GAS_URL not set — data layer will fail")

    await _seed_superuser()
    logger.info("Superuser seeded")

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(_send_daily_horoscope_emails, "cron", hour=6, minute=0)
    scheduler.start()
    logger.info("Daily email scheduler started")

    yield

    scheduler.shutdown(wait=False)


class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=604800"
        return response


app = FastAPI(
    title="Zodovia API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan
)

app.add_middleware(CacheControlMiddleware)

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


frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
static_dir   = os.path.join(frontend_dir, "static")

if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    return FileResponse(os.path.join(frontend_dir, "robots.txt"), media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml():
    return FileResponse(os.path.join(frontend_dir, "sitemap.xml"), media_type="application/xml")


def _html(path: str) -> Response:
    return FileResponse(path, headers={"Cache-Control": "no-cache, no-store, must-revalidate",
                                       "Pragma": "no-cache"})


@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    clean = full_path.strip("/")
    direct = os.path.join(frontend_dir, clean)
    if os.path.isfile(direct):
        return FileResponse(direct)

    page_map = {
        "": "index.html", "chart": "chart.html", "dashboard": "dashboard.html",
        "compatibility": "compatibility.html", "admin": "admin.html",
        "pricing": "pricing.html", "terms": "terms.html",
        "privacy": "privacy.html", "refund": "refund.html",
        "forgot-password": "forgot-password.html",
        "reset-password": "reset-password.html",
    }
    filename = page_map.get(clean, "index.html")
    filepath = os.path.join(frontend_dir, filename)
    if os.path.isfile(filepath):
        return _html(filepath)
    return _html(os.path.join(frontend_dir, "index.html"))
