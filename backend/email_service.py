import os
import html
import logging
import resend

logger = logging.getLogger(__name__)

_RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@zodovia.com")
APP_URL = os.getenv("APP_URL", "https://www.zodovia.com")

resend.api_key = _RESEND_API_KEY

_BASE_STYLE = """
  <style>
    body{margin:0;padding:0;background:#0d0017;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}
    a{color:#d4af37;}
  </style>
"""

_FOOTER = f"""
<p style="color:#5c3d7a;font-size:0.75rem;text-align:center;margin-top:16px;">
  &copy; 2026 Zodovia &nbsp;·&nbsp;
  <a href="{APP_URL}/privacy" style="color:#7c5fa0;">Privacy</a>
  &nbsp;·&nbsp;
  <a href="{APP_URL}/dashboard" style="color:#7c5fa0;">Dashboard</a>
</p>
"""

_HEADER = """
<div style="background:linear-gradient(135deg,#1a0533,#0d0017);padding:28px 32px;text-align:center;border-bottom:1px solid rgba(212,175,55,0.15);">
  <div style="font-size:1.8rem;margin-bottom:6px;">✨</div>
  <div style="color:#d4af37;font-size:1.35rem;font-weight:700;letter-spacing:1px;">ZODOVIA</div>
</div>
"""


def _send(to: str, subject: str, html: str) -> bool:
    if not _RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — email skipped for %s", to)
        return False
    try:
        resend.Emails.send({
            "from": f"Zodovia <{FROM_EMAIL}>",
            "to": [to],
            "subject": subject,
            "html": html,
        })
        logger.info("Email sent: %s → %s", subject[:40], to)
        return True
    except Exception as exc:
        logger.error("Email send failed to %s: %s", to, exc)
        return False


def send_password_reset_email(to_email: str, name: str, reset_token: str) -> bool:
    safe_name = html.escape(name)
    reset_url = f"{APP_URL}/reset-password?token={reset_token}"
    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">{_BASE_STYLE}</head>
<body>
<div style="max-width:520px;margin:40px auto;padding:0 16px;">
  <div style="background:#1a0533;border:1px solid rgba(212,175,55,0.3);border-radius:16px;overflow:hidden;">
    {_HEADER}
    <div style="padding:32px;">
      <h2 style="color:#f0e6ff;margin:0 0 10px;font-size:1.25rem;">Reset Your Password</h2>
      <p style="color:#a78bca;margin:0 0 24px;line-height:1.65;">
        Hi {safe_name}, we received a request to reset your Zodovia password.
        Click the button below to choose a new one.
      </p>
      <div style="text-align:center;margin:28px 0;">
        <a href="{reset_url}"
           style="display:inline-block;background:#d4af37;color:#1a0533;font-weight:700;
                  padding:14px 32px;border-radius:8px;text-decoration:none;font-size:1rem;">
          Reset Password →
        </a>
      </div>
      <p style="color:#7c5fa0;font-size:0.82rem;margin:0;text-align:center;">
        This link expires in <strong style="color:#a78bca;">1 hour</strong>.
        If you didn't request this, you can safely ignore it.
      </p>
      <hr style="border:none;border-top:1px solid rgba(212,175,55,0.1);margin:20px 0;">
      <p style="color:#5c3d7a;font-size:0.76rem;text-align:center;margin:0;word-break:break-all;">
        Or copy: <a href="{reset_url}" style="color:#7c5fa0;">{reset_url}</a>
      </p>
    </div>
  </div>
  {_FOOTER}
</div>
</body>
</html>"""
    return _send(to_email, "Reset your Zodovia password", html_body)


def send_daily_horoscope_email(
    to_email: str,
    name: str,
    sun_sign: str,
    horoscope: str,
    intention: str | None,
    date_str: str,
) -> bool:
    paragraphs_html = ""
    for block in horoscope.strip().split("\n\n"):
        b = block.strip()
        if b and not b.startswith("---") and not b.startswith("### ") and not b.startswith("## "):
            safe = b.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ")
            paragraphs_html += f'<p style="color:#c4a0e8;line-height:1.7;margin:0 0 14px;">{safe}</p>'

    intention_html = ""
    if intention:
        safe_intention = intention.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        intention_html = f"""
        <div style="background:rgba(212,175,55,0.08);border-left:3px solid #d4af37;
                    padding:14px 18px;border-radius:0 8px 8px 0;margin-top:20px;">
          <div style="color:#d4af37;font-size:0.78rem;font-weight:600;text-transform:uppercase;
                      letter-spacing:1px;margin-bottom:6px;">🌱 Today's Intention</div>
          <p style="color:#f0e6ff;margin:0;font-style:italic;line-height:1.6;">{safe_intention}</p>
        </div>"""

    safe_name = html.escape(name)
    safe_sign = html.escape(sun_sign)
    safe_date = html.escape(date_str)

    _unsubscribe = f"""
<p style="color:#3d2a55;font-size:0.72rem;text-align:center;margin-top:12px;">
  You're receiving this because you have an active Zodovia Premium subscription.<br>
  To stop these emails, <a href="{APP_URL}/dashboard" style="color:#5c3d7a;">manage your preferences</a> in your dashboard.
</p>"""

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">{_BASE_STYLE}</head>
<body>
<div style="max-width:580px;margin:40px auto;padding:0 16px;">
  <div style="background:#1a0533;border:1px solid rgba(212,175,55,0.3);border-radius:16px;overflow:hidden;">
    <div style="background:linear-gradient(135deg,#1a0533,#0d0017);padding:28px 32px;
                text-align:center;border-bottom:1px solid rgba(212,175,55,0.15);">
      <div style="font-size:1.8rem;margin-bottom:6px;">✨</div>
      <div style="color:#d4af37;font-size:1.35rem;font-weight:700;letter-spacing:1px;">ZODOVIA</div>
      <p style="color:#a78bca;margin:8px 0 0;font-size:0.86rem;">{safe_date}</p>
    </div>
    <div style="padding:32px;">
      <h2 style="color:#f0e6ff;margin:0 0 4px;font-size:1.15rem;">🌟 Your Daily Reading</h2>
      <p style="color:#7c5fa0;margin:0 0 20px;font-size:0.88rem;">{safe_name} &nbsp;·&nbsp; {safe_sign} Sun</p>
      {paragraphs_html}
      {intention_html}
      <div style="text-align:center;margin-top:28px;">
        <a href="{APP_URL}/dashboard"
           style="display:inline-block;background:#d4af37;color:#1a0533;font-weight:700;
                  padding:13px 28px;border-radius:8px;text-decoration:none;font-size:0.95rem;">
          View Full Dashboard →
        </a>
      </div>
    </div>
  </div>
  {_FOOTER}
  {_unsubscribe}
</div>
</body>
</html>"""
    return _send(to_email, f"🌟 Your daily reading is ready, {safe_name}", html_body)
