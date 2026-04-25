"""
AquaGuard Alert Service
=======================
Sends personalized HTML email alerts to registered users when high-risk
ocean conditions are detected at their saved location.

Flow:
  1. Scheduler runs pipeline for each monitored location
  2. If risk is High OR bloom/oil spill detected → send_alert() is called
  3. We load all users from outputs/users.json
  4. Each user has a `location` field (set at signup or via profile)
  5. If the alert location matches a user's location → email that user
  6. If a user has no location set → email them for ALL alerts (global subscriber)
  7. Alert is always saved to outputs/alert_history.json regardless of email
"""

import smtplib
import os
import json
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from utils.logger import get_logger

logger = get_logger(__name__)

ALERT_HISTORY_FILE = "outputs/alert_history.json"
USERS_FILE         = "outputs/users.json"


def _save_alert_history(location: str, prediction: dict, environment: dict, species: dict = None):
    """Append alert entry to history file (newest first, max 200)."""
    os.makedirs("outputs", exist_ok=True)
    history = []
    if os.path.exists(ALERT_HISTORY_FILE):
        try:
            with open(ALERT_HISTORY_FILE) as f:
                history = json.load(f)
        except Exception:
            history = []

    entry = {
        "timestamp":          datetime.now(timezone.utc).isoformat(),
        "location":           location,
        "risk_label":         prediction.get("risk_label", "N/A"),
        "bloom_detected":     prediction.get("bloom_detected", False),
        "oil_spill_detected": prediction.get("oil_spill_detected", False),
        "temperature":        environment.get("temperature"),
        "chlorophyll":        environment.get("chlorophyll"),
        "threatened_count":   species.get("threatened_count", 0) if species else 0,
        "harmed_count":       species.get("harmed_count", 0) if species else 0,
    }
    history.insert(0, entry)
    history = history[:200]
    with open(ALERT_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, default=str)


def _load_users() -> dict:
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _location_matches(user_location: str, alert_location: str) -> bool:
    """
    Fuzzy match: user's saved location vs the alert location.
    e.g. user saved "Kerala Coast" matches alert for "Kerala Coast"
    """
    if not user_location:
        return True   # no location set → receive all alerts
    return user_location.strip().lower() in alert_location.strip().lower() or \
           alert_location.strip().lower() in user_location.strip().lower()


def _build_html_email(user_name: str, location: str, prediction: dict,
                       environment: dict, species: dict) -> str:
    """Build a rich HTML email body."""
    risk_label  = prediction.get("risk_label", "Unknown")
    risk_color  = "#ff4d4d" if risk_label == "High" else "#00ff88"
    bloom       = prediction.get("bloom_detected", False)
    oil         = prediction.get("oil_spill_detected", False)
    temp        = environment.get("temperature", "N/A")
    chl         = environment.get("chlorophyll", "N/A")
    turbidity   = environment.get("turbidity", "N/A")
    source      = environment.get("source", "N/A")
    date_range  = environment.get("date_range", "N/A")
    rule        = prediction.get("rule_based_risk", {})
    factors     = ", ".join(rule.get("contributing_factors", [])) or "None"
    sar         = prediction.get("sar_value", "N/A")
    now         = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sp_total     = species.get("total_found", 0) if species else 0
    sp_threatened = species.get("threatened_count", 0) if species else 0
    sp_harmed    = species.get("harmed_count", 0) if species else 0

    # Build harmed species rows
    harmed_rows = ""
    if species:
        for s in (species.get("currently_harmed") or [])[:8]:
            reasons = "; ".join(s.get("harm_reasons", []))
            harmed_rows += f"""
            <tr>
              <td style="padding:8px 12px;border-bottom:1px solid #0a2a40;font-style:italic">{s['name']}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #0a2a40;color:#ffaa00">{s.get('iucn_status','DD')}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #0a2a40;color:#ff6b6b;font-size:12px">{reasons}</td>
            </tr>"""

    # Alert badges
    badges = ""
    if risk_label == "High":
        badges += '<span style="background:#ff4d4d;color:#fff;padding:4px 12px;font-size:12px;margin-right:8px;font-weight:600">HIGH RISK</span>'
    if bloom:
        badges += '<span style="background:#ffaa00;color:#000;padding:4px 12px;font-size:12px;margin-right:8px;font-weight:600">ALGAL BLOOM</span>'
    if oil:
        badges += '<span style="background:#ff4d4d;color:#fff;padding:4px 12px;font-size:12px;margin-right:8px;font-weight:600">OIL SPILL</span>'

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#020d18;font-family:Arial,sans-serif;color:#e0f0ff">
  <div style="max-width:600px;margin:0 auto;background:#041525;border:1px solid rgba(0,212,255,0.2)">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#041525,#062d52);padding:28px 32px;border-bottom:2px solid #00d4ff">
      <div style="font-size:22px;font-weight:700;color:#00d4ff;letter-spacing:1px">◈ OceanSense</div>
      <div style="font-size:11px;letter-spacing:3px;color:#4a7a9b;margin-top:4px">OCEAN INTELLIGENCE PLATFORM</div>
    </div>

    <!-- Alert title -->
    <div style="padding:24px 32px;border-bottom:1px solid rgba(0,212,255,0.1)">
      <div style="font-size:13px;color:#4a7a9b;margin-bottom:8px">REAL-TIME OCEAN ALERT</div>
      <div style="font-size:24px;font-weight:700;color:#fff;margin-bottom:12px">🚨 {location}</div>
      <div>{badges}</div>
      <div style="font-size:12px;color:#4a7a9b;margin-top:12px">Generated: {now} &nbsp;·&nbsp; Source: {source} &nbsp;·&nbsp; Period: {date_range}</div>
    </div>

    <!-- Greeting -->
    <div style="padding:20px 32px 0">
      <p style="color:#8ab4cc;font-size:14px;line-height:1.6">
        Hi <b style="color:#fff">{user_name}</b>, a high-risk ocean condition has been detected at your monitored location.
        Here is the full satellite analysis:
      </p>
    </div>

    <!-- Environmental params -->
    <div style="padding:20px 32px">
      <div style="font-size:11px;letter-spacing:2px;color:#4a7a9b;margin-bottom:12px">ENVIRONMENTAL PARAMETERS</div>
      <table style="width:100%;border-collapse:collapse">
        <tr>
          <td style="padding:10px 14px;background:rgba(0,60,100,0.3);border:1px solid rgba(0,212,255,0.1);font-size:12px;color:#4a7a9b">SEA SURFACE TEMP</td>
          <td style="padding:10px 14px;background:rgba(0,60,100,0.3);border:1px solid rgba(0,212,255,0.1);font-size:18px;font-weight:700;color:#00d4ff">{temp} °C</td>
          <td style="padding:10px 14px;background:rgba(0,60,100,0.3);border:1px solid rgba(0,212,255,0.1);font-size:12px;color:#4a7a9b">CHLOROPHYLL-A</td>
          <td style="padding:10px 14px;background:rgba(0,60,100,0.3);border:1px solid rgba(0,212,255,0.1);font-size:18px;font-weight:700;color:#00ff88">{chl} mg/m³</td>
        </tr>
        <tr>
          <td style="padding:10px 14px;background:rgba(0,60,100,0.2);border:1px solid rgba(0,212,255,0.1);font-size:12px;color:#4a7a9b">TURBIDITY</td>
          <td style="padding:10px 14px;background:rgba(0,60,100,0.2);border:1px solid rgba(0,212,255,0.1);font-size:18px;font-weight:700;color:#00d4ff">{turbidity}</td>
          <td style="padding:10px 14px;background:rgba(0,60,100,0.2);border:1px solid rgba(0,212,255,0.1);font-size:12px;color:#4a7a9b">SAR BACKSCATTER</td>
          <td style="padding:10px 14px;background:rgba(0,60,100,0.2);border:1px solid rgba(0,212,255,0.1);font-size:18px;font-weight:700;color:#00d4ff">{sar} dB</td>
        </tr>
      </table>
    </div>

    <!-- ML predictions -->
    <div style="padding:0 32px 20px">
      <div style="font-size:11px;letter-spacing:2px;color:#4a7a9b;margin-bottom:12px">ML MODEL PREDICTIONS</div>
      <table style="width:100%;border-collapse:collapse">
        <tr>
          <td style="padding:10px 14px;border:1px solid rgba(0,212,255,0.1);font-size:12px;color:#4a7a9b">ECOSYSTEM RISK</td>
          <td style="padding:10px 14px;border:1px solid rgba(0,212,255,0.1);font-weight:700;color:{risk_color}">{risk_label}</td>
          <td style="padding:10px 14px;border:1px solid rgba(0,212,255,0.1);font-size:12px;color:#4a7a9b">ALGAL BLOOM</td>
          <td style="padding:10px 14px;border:1px solid rgba(0,212,255,0.1);font-weight:700;color:{'#ff4d4d' if bloom else '#00ff88'}">{'⚠ DETECTED' if bloom else 'Clear'}</td>
        </tr>
        <tr>
          <td style="padding:10px 14px;border:1px solid rgba(0,212,255,0.1);font-size:12px;color:#4a7a9b">OIL SPILL</td>
          <td style="padding:10px 14px;border:1px solid rgba(0,212,255,0.1);font-weight:700;color:{'#ff4d4d' if oil else '#00ff88'}">{'⚠ DETECTED' if oil else 'Clear'}</td>
          <td style="padding:10px 14px;border:1px solid rgba(0,212,255,0.1);font-size:12px;color:#4a7a9b">RISK FACTORS</td>
          <td style="padding:10px 14px;border:1px solid rgba(0,212,255,0.1);font-size:12px;color:#8ab4cc">{factors}</td>
        </tr>
      </table>
    </div>

    <!-- Species impact -->
    <div style="padding:0 32px 20px">
      <div style="font-size:11px;letter-spacing:2px;color:#4a7a9b;margin-bottom:12px">MARINE SPECIES IMPACT</div>
      <div style="display:flex;gap:16px;margin-bottom:14px">
        <div style="background:rgba(0,60,100,0.3);border:1px solid rgba(0,212,255,0.1);padding:12px 20px;text-align:center;flex:1">
          <div style="font-size:24px;font-weight:700;color:#00d4ff">{sp_total}</div>
          <div style="font-size:10px;color:#4a7a9b;letter-spacing:1px">SPECIES FOUND</div>
        </div>
        <div style="background:rgba(0,60,100,0.3);border:1px solid rgba(0,212,255,0.1);padding:12px 20px;text-align:center;flex:1">
          <div style="font-size:24px;font-weight:700;color:#ffaa00">{sp_threatened}</div>
          <div style="font-size:10px;color:#4a7a9b;letter-spacing:1px">THREATENED</div>
        </div>
        <div style="background:rgba(0,60,100,0.3);border:1px solid rgba(0,212,255,0.1);padding:12px 20px;text-align:center;flex:1">
          <div style="font-size:24px;font-weight:700;color:#ff4d4d">{sp_harmed}</div>
          <div style="font-size:10px;color:#4a7a9b;letter-spacing:1px">CURRENTLY HARMED</div>
        </div>
      </div>
      {f'''<table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead>
          <tr style="background:rgba(0,40,70,0.5)">
            <th style="padding:8px 12px;text-align:left;color:#4a7a9b;font-size:10px;letter-spacing:2px">SPECIES</th>
            <th style="padding:8px 12px;text-align:left;color:#4a7a9b;font-size:10px;letter-spacing:2px">STATUS</th>
            <th style="padding:8px 12px;text-align:left;color:#4a7a9b;font-size:10px;letter-spacing:2px">HARM REASON</th>
          </tr>
        </thead>
        <tbody>{harmed_rows}</tbody>
      </table>''' if harmed_rows else '<div style="color:#4a7a9b;font-size:13px;padding:8px 0">No harmed species detected under current conditions.</div>'}
    </div>

    <!-- Footer -->
    <div style="padding:20px 32px;border-top:1px solid rgba(0,212,255,0.1);background:rgba(0,10,20,0.5)">
      <p style="font-size:11px;color:#4a7a9b;line-height:1.7;margin:0">
        This is an automated alert from <b style="color:#00d4ff">OceanSense Ocean Intelligence Platform</b>.<br>
        Data sources: NASA MODIS · NOAA OISST · Copernicus Sentinel-1 · GBIF · IUCN Red List<br>
        To change your alert location or email, log in to OceanSense and update your profile.
      </p>
    </div>

  </div>
</body>
</html>"""


def _should_alert(prediction: dict, environment: dict) -> bool:
    """Return True if conditions warrant sending an alert."""
    return (
        prediction.get("risk_label") == "High" or
        prediction.get("risk") == 1 or
        prediction.get("bloom_detected") is True or
        prediction.get("oil_spill_detected") is True
    )


def send_alert(location: str, prediction: dict, environment: dict, species: dict = None):
    """
    Send personalized HTML email alerts to users whose saved location
    matches the alert location. Users with no location set receive all alerts.

    Always saves to alert history regardless of email success.
    """
    # Always persist to history first
    _save_alert_history(location, prediction, environment, species)

    if not _should_alert(prediction, environment):
        logger.info(f"No alert needed for {location} — conditions normal")
        return

    sender   = os.getenv("ALERT_EMAIL_SENDER")
    password = os.getenv("ALERT_EMAIL_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if not sender or not password:
        logger.warning(
            f"Alert for {location} saved to history but NOT emailed — "
            "ALERT_EMAIL_SENDER or ALERT_EMAIL_PASSWORD not set in .env"
        )
        return

    users = _load_users()
    if not users:
        logger.warning("No registered users — alert saved to history only")
        return

    # Find users who should receive this alert
    recipients = []
    for user in users.values():
        user_loc = user.get("location", "")
        if _location_matches(user_loc, location):
            recipients.append({
                "name":        user.get("name", "User"),
                "alert_email": user.get("alert_email") or user.get("email"),
            })

    if not recipients:
        logger.info(f"No users subscribed to location '{location}' — alert saved to history only")
        return

    risk_label = prediction.get("risk_label", "High")
    subject    = f"🚨 OceanSense Alert — {risk_label} Risk at {location}"

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(sender, password)

            for recipient in recipients:
                html_body = _build_html_email(
                    user_name=recipient["name"],
                    location=location,
                    prediction=prediction,
                    environment=environment,
                    species=species or {}
                )
                msg = MIMEMultipart("alternative")
                msg["From"]    = f"OceanSense Alerts <{sender}>"
                msg["To"]      = recipient["alert_email"]
                msg["Subject"] = subject
                msg.attach(MIMEText(html_body, "html"))

                server.sendmail(sender, recipient["alert_email"], msg.as_string())
                logger.info(f"Alert emailed to {recipient['alert_email']} for {location}")

    except Exception as e:
        logger.error(f"Failed to send alert emails: {e}")


def send_pollution_alert(location: str, pollution: dict, environment: dict):
    """
    Send a dedicated pollution discharge alert email.
    Called when pollution_service detects a sudden discharge event.
    Always saves to alert history.
    """
    # Save to alert history with pollution flag
    _save_alert_history(location, {
        "risk_label": pollution.get("overall_severity", "High"),
        "bloom_detected": False,
        "oil_spill_detected": any(e["type"] == "sar_slick" for e in pollution.get("events", [])),
        "pollution_detected": True,
        "pollution_events": pollution.get("events", []),
    }, environment)

    sender    = os.getenv("ALERT_EMAIL_SENDER")
    password  = os.getenv("ALERT_EMAIL_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if not sender or not password:
        logger.warning(f"Pollution alert for {location} saved but NOT emailed — SMTP not configured")
        return

    users = _load_users()
    recipients = [
        {"name": u.get("name", "User"), "alert_email": u.get("alert_email") or u.get("email")}
        for u in users.values()
        if _location_matches(u.get("location", ""), location)
    ]
    if not recipients:
        logger.info(f"No users subscribed to '{location}' — pollution alert saved to history only")
        return

    severity      = pollution.get("overall_severity", "High")
    events        = pollution.get("events", [])
    now           = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    temp          = environment.get("temperature", "N/A")
    chl           = environment.get("chlorophyll", "N/A")
    turb          = environment.get("turbidity", "N/A")
    source        = environment.get("source", "Satellite")
    sev_color     = {"Critical": "#cc0000", "High": "#ff4d4d", "Moderate": "#ff8c00"}.get(severity, "#ff4d4d")

    event_rows = ""
    for e in events:
        event_rows += f"""
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid #0a2a40;font-weight:600;color:#ff8c00">{e['name']}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #0a2a40;color:{sev_color};font-weight:700">{e['severity']}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #0a2a40;font-size:12px;color:#8ab4cc">{e['evidence']}</td>
        </tr>
        <tr>
          <td colspan="3" style="padding:6px 14px 12px;border-bottom:1px solid #0a2a40;font-size:12px;color:#4a7a9b;font-style:italic">{e['description']}</td>
        </tr>"""

    subject = f"⚠ OceanSense Pollution Alert — {severity} Discharge at {location}"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#020d18;font-family:Arial,sans-serif;color:#e0f0ff">
<div style="max-width:600px;margin:0 auto;background:#041525;border:1px solid rgba(255,100,0,0.4)">
  <div style="background:linear-gradient(135deg,#1a0800,#3a1000);padding:28px 32px;border-bottom:2px solid #ff4d4d">
    <div style="font-size:22px;font-weight:700;color:#00d4ff;letter-spacing:1px">◈ OceanSense</div>
    <div style="font-size:11px;letter-spacing:3px;color:#4a7a9b;margin-top:4px">OCEAN INTELLIGENCE PLATFORM</div>
  </div>
  <div style="padding:24px 32px;border-bottom:1px solid rgba(255,100,0,0.2)">
    <div style="font-size:13px;color:#ff8c00;margin-bottom:8px;letter-spacing:2px">⚠ POLLUTION DISCHARGE ALERT</div>
    <div style="font-size:26px;font-weight:700;color:#fff;margin-bottom:12px">{location}</div>
    <span style="background:{sev_color};color:#fff;padding:5px 16px;font-size:13px;font-weight:700">{severity.upper()} SEVERITY</span>
    <div style="font-size:12px;color:#4a7a9b;margin-top:14px">Detected: {now} &nbsp;·&nbsp; Source: {source}</div>
  </div>
  <div style="padding:20px 32px">
    <p style="color:#8ab4cc;font-size:14px;line-height:1.7">
      A <b style="color:{sev_color}">{severity}</b> pollution discharge event has been detected at
      <b style="color:#fff">{location}</b> based on satellite analysis. Sudden changes in ocean
      parameters indicate possible pollutant discharge into this region.
    </p>
  </div>
  <div style="padding:0 32px 20px">
    <div style="font-size:11px;letter-spacing:2px;color:#4a7a9b;margin-bottom:12px">DETECTED POLLUTION EVENTS</div>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="background:rgba(60,10,0,0.5)">
          <th style="padding:8px 14px;text-align:left;color:#ff8c00;font-size:10px;letter-spacing:2px">TYPE</th>
          <th style="padding:8px 14px;text-align:left;color:#ff8c00;font-size:10px;letter-spacing:2px">SEVERITY</th>
          <th style="padding:8px 14px;text-align:left;color:#ff8c00;font-size:10px;letter-spacing:2px">EVIDENCE</th>
        </tr>
      </thead>
      <tbody>{event_rows}</tbody>
    </table>
  </div>
  <div style="padding:0 32px 20px">
    <div style="font-size:11px;letter-spacing:2px;color:#4a7a9b;margin-bottom:12px">CURRENT SATELLITE READINGS</div>
    <table style="width:100%;border-collapse:collapse">
      <tr>
        <td style="padding:10px 14px;background:rgba(60,10,0,0.3);border:1px solid rgba(255,100,0,0.15);font-size:12px;color:#4a7a9b">SST</td>
        <td style="padding:10px 14px;background:rgba(60,10,0,0.3);border:1px solid rgba(255,100,0,0.15);font-weight:700;color:#00d4ff">{temp} °C</td>
        <td style="padding:10px 14px;background:rgba(60,10,0,0.3);border:1px solid rgba(255,100,0,0.15);font-size:12px;color:#4a7a9b">CHLOROPHYLL</td>
        <td style="padding:10px 14px;background:rgba(60,10,0,0.3);border:1px solid rgba(255,100,0,0.15);font-weight:700;color:#00ff88">{chl} mg/m³</td>
      </tr>
      <tr>
        <td style="padding:10px 14px;background:rgba(60,10,0,0.2);border:1px solid rgba(255,100,0,0.15);font-size:12px;color:#4a7a9b">TURBIDITY</td>
        <td colspan="3" style="padding:10px 14px;background:rgba(60,10,0,0.2);border:1px solid rgba(255,100,0,0.15);font-weight:700;color:#ff8c00">{turb}</td>
      </tr>
    </table>
  </div>
  <div style="padding:20px 32px;border-top:1px solid rgba(255,100,0,0.15);background:rgba(0,10,20,0.5)">
    <p style="font-size:11px;color:#4a7a9b;line-height:1.7;margin:0">
      Automated alert from <b style="color:#00d4ff">OceanSense</b> · NASA MODIS · NOAA OISST · Copernicus Sentinel-1<br>
      This alert is based on satellite anomaly detection. Ground-truth verification is recommended.
    </p>
  </div>
</div>
</body></html>"""

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(sender, password)
            for recipient in recipients:
                msg = MIMEMultipart("alternative")
                msg["From"]    = f"OceanSense Alerts <{sender}>"
                msg["To"]      = recipient["alert_email"]
                msg["Subject"] = subject
                msg.attach(MIMEText(html.replace("{user_name}", recipient["name"]), "html"))
                server.sendmail(sender, recipient["alert_email"], msg.as_string())
                logger.info(f"Pollution alert emailed to {recipient['alert_email']} for {location}")
    except Exception as e:
        logger.error(f"Failed to send pollution alert: {e}")


def send_test_alert(to_email: str, user_name: str = "Test User") -> dict:
    """
    Send a test alert email with dummy data to verify SMTP config works.
    Returns {"success": bool, "message": str}
    """
    sender   = os.getenv("ALERT_EMAIL_SENDER")
    password = os.getenv("ALERT_EMAIL_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if not sender or not password:
        return {"success": False, "message": "ALERT_EMAIL_SENDER or ALERT_EMAIL_PASSWORD not set in .env"}

    dummy_prediction = {
        "risk_label": "High", "risk": 1,
        "bloom_detected": True, "oil_spill_detected": False,
        "bloom_confidence": 0.91, "risk_confidence": 0.87,
        "sar_value": -18.4,
        "rule_based_risk": {
            "risk_label": "High", "risk_score": 0.82,
            "contributing_factors": ["High chlorophyll (6.2 mg/m³)", "Elevated SST (29.1°C)"]
        }
    }
    dummy_environment = {
        "temperature": 29.1, "chlorophyll": 6.2, "turbidity": 0.45,
        "source": "TEST DATA", "date_range": "2026-03-15 to 2026-03-22"
    }
    dummy_species = {
        "total_found": 12, "threatened_count": 3, "harmed_count": 2,
        "currently_harmed": [
            {"name": "Acropora palmata", "iucn_status": "CR",
             "harm_reasons": ["Elevated SST (29.1°C) — thermal stress, coral bleaching risk"]},
            {"name": "Tursiops truncatus", "iucn_status": "LC",
             "harm_reasons": ["Active algal bloom — HAB toxin exposure"]}
        ]
    }

    try:
        html_body = _build_html_email(
            user_name=user_name,
            location="Test Location (Arabian Sea)",
            prediction=dummy_prediction,
            environment=dummy_environment,
            species=dummy_species
        )
        msg = MIMEMultipart("alternative")
        msg["From"]    = f"OceanSense Alerts <{sender}>"
        msg["To"]      = to_email
        msg["Subject"] = "🧪 OceanSense — Test Alert Email"
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, to_email, msg.as_string())

        return {"success": True, "message": f"Test alert sent to {to_email}"}
    except Exception as e:
        return {"success": False, "message": str(e)}
