import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pipeline.prediction_pipeline import run_prediction_pipeline
from agents.ocean_agent import OceanAgent
from dotenv import load_dotenv
from datetime import datetime, timezone
import json, threading, hashlib, secrets, time, asyncio
from collections import defaultdict
from utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

SCHEDULER_RESULTS_FILE  = "outputs/scheduler_results.json"
ALERT_HISTORY_FILE      = "outputs/alert_history.json"
CUSTOM_LOCATIONS_FILE   = "outputs/custom_locations.json"
USERS_FILE              = "outputs/users.json"

_scheduler_running  = False
_scheduler_progress = ""

# ── Simple TTL cache ───────────────────────────────────────────────────────────
_cache: dict = {}          # key → (value, expires_at)
CACHE_TTL = 120            # 2 minutes
_search_history = []      # Last 10 searches
SEARCH_HISTORY_FILE = "outputs/search_history.json"

def _cache_get(key: str):
    entry = _cache.get(key)
    if entry and time.time() < entry[1]:
        return entry[0]
    _cache.pop(key, None)
    return None

def _cache_set(key: str, value, ttl: int = CACHE_TTL):
    _cache[key] = (value, time.time() + ttl)

# ── Rate limiter (in-memory, per IP) ──────────────────────────────────────────
_rate_store: dict = defaultdict(list)   # ip → [timestamps]
RATE_LIMIT   = 60    # requests
RATE_WINDOW  = 60    # seconds

def _check_rate(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _rate_store[ip] if now - t < RATE_WINDOW]
    _rate_store[ip] = hits
    if len(hits) >= RATE_LIMIT:
        return False
    _rate_store[ip].append(now)
    return True

# ── Metrics counters ───────────────────────────────────────────────────────────
_metrics = {
    "requests_total":    0,
    "search_calls":      0,
    "agent_calls":       0,
    "cache_hits":        0,
    "cache_misses":      0,
    "rate_limited":      0,
    "errors_total":      0,
    "started_at":        datetime.now(timezone.utc).isoformat(),
}

# ── WebSocket connection manager ───────────────────────────────────────────────
class _WSManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)

ws_manager = _WSManager()

# ── Auth helpers ───────────────────────────────────────────────────────────────
def _load_users() -> dict:
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_users(users: dict):
    os.makedirs("outputs", exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def _make_token() -> str:
    return secrets.token_hex(32)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="OceanSense API",
    description="Real-time ocean health monitoring — algal bloom, oil spill, species risk",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:8000", "http://127.0.0.1:8000"
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate-limit middleware ──────────────────────────────────────────────────────
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    _metrics["requests_total"] += 1
    ip = request.client.host if request.client else "unknown"
    # Skip rate limiting for WebSocket and health
    if request.url.path not in ("/health", "/ws/alerts", "/metrics"):
        if not _check_rate(ip):
            _metrics["rate_limited"] += 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Max 60 requests/minute."}
            )
    response = await call_next(request)
    if response.status_code >= 500:
        _metrics["errors_total"] += 1
    return response

_agent: OceanAgent | None = None

def _get_agent() -> OceanAgent:
    global _agent
    if _agent is None:
        _agent = OceanAgent()
    return _agent


class AgentQuery(BaseModel):
    query: str
    language: str = "en"  # en, hi, mr

class SignupBody(BaseModel):
    name: str
    email: str
    password: str
    alert_email: str | None = None
    location: str | None = None

class LoginBody(BaseModel):
    email: str
    password: str

class UpdateProfileBody(BaseModel):
    token: str
    alert_email: str | None = None
    name: str | None = None
    location: str | None = None


# ── Auth endpoints ─────────────────────────────────────────────────────────────
@app.post("/auth/signup")
def signup(body: SignupBody):
    users = _load_users()
    email = body.email.strip().lower()
    if email in users:
        raise HTTPException(status_code=400, detail="Email already registered")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    token = _make_token()
    users[email] = {
        "name":        body.name.strip(),
        "email":       email,
        "password":    _hash_password(body.password),
        "token":       token,
        "alert_email": (body.alert_email or email).strip().lower(),
        "location":    body.location.strip() if body.location else "",
        "created_at":  datetime.now(timezone.utc).isoformat()
    }
    _save_users(users)
    return {
        "status": "ok", "token": token,
        "name": body.name.strip(), "email": email,
        "alert_email": (body.alert_email or email).strip().lower(),
        "location": body.location or ""
    }


@app.post("/auth/login")
def login(body: LoginBody):
    users = _load_users()
    email = body.email.strip().lower()
    user  = users.get(email)
    if not user or user["password"] != _hash_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = _make_token()
    user["token"] = token
    _save_users(users)
    return {"status": "ok", "token": token, "name": user["name"], "email": email,
            "alert_email": user.get("alert_email", email), "location": user.get("location", "")}


@app.post("/auth/update")
def update_profile(body: UpdateProfileBody):
    users = _load_users()
    user = next((u for u in users.values() if u.get("token") == body.token), None)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session token")
    if body.alert_email:
        user["alert_email"] = body.alert_email.strip().lower()
    if body.name:
        user["name"] = body.name.strip()
    if body.location is not None:
        user["location"] = body.location.strip()
    _save_users(users)
    return {"status": "updated", "alert_email": user["alert_email"],
            "name": user["name"], "location": user.get("location", "")}


@app.get("/auth/me")
def get_me(token: str):
    users = _load_users()
    user  = next((u for u in users.values() if u.get("token") == token), None)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"name": user["name"], "email": user["email"],
            "alert_email": user.get("alert_email", user["email"]),
            "location": user.get("location", "")}


# ── Search (with cache) ────────────────────────────────────────────────────────
@app.get("/search")
def search(location: str):
    if not location or not location.strip():
        raise HTTPException(status_code=400, detail="Location parameter is required")

    cache_key = f"search:{location.strip().lower()}"
    cached = _cache_get(cache_key)
    if cached:
        _metrics["cache_hits"] += 1
        return {**cached, "_cached": True}

    _metrics["cache_misses"] += 1
    _metrics["search_calls"] += 1
    result = run_prediction_pipeline(location.strip())
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    _cache_set(cache_key, result)
    
    # Update history
    loc_trimmed = location.strip()
    if loc_trimmed not in _search_history:
        _search_history.insert(0, loc_trimmed)
        if len(_search_history) > 10:
            _search_history.pop()
        # Persist history
        os.makedirs("outputs", exist_ok=True)
        with open(SEARCH_HISTORY_FILE, "w") as f:
            json.dump(_search_history, f)
            
    return result


@app.get("/search/history")
def get_search_history():
    global _search_history
    if not _search_history and os.path.exists(SEARCH_HISTORY_FILE):
        try:
            with open(SEARCH_HISTORY_FILE) as f:
                _search_history = json.load(f)
        except Exception:
            pass
    return {"history": _search_history}


# ── Agent ──────────────────────────────────────────────────────────────────────
_LANG_PROMPTS = {
    "hi": "Please respond in Hindi (हिंदी). Use clear formatting with bullet points where helpful.",
    "mr": "Please respond in Marathi (मराठी). Use clear formatting with bullet points where helpful.",
    "en": "",
}

@app.post("/agent")
def agent_query(body: AgentQuery):
    if not body.query or not body.query.strip():
        raise HTTPException(status_code=400, detail="query field is required")
    _metrics["agent_calls"] += 1
    try:
        lang_prefix = _LANG_PROMPTS.get(body.language, "")
        query = f"{lang_prefix}\n\n{body.query.strip()}" if lang_prefix else body.query.strip()
        answer = _get_agent().run(query)
        return {"query": body.query, "answer": answer, "language": body.language}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Report ─────────────────────────────────────────────────────────────────────
@app.get("/report")
def generate_report(location: str):
    if not location or not location.strip():
        raise HTTPException(status_code=400, detail="Location parameter is required")

    result = run_prediction_pipeline(location.strip())
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    env    = result.get("environment", {})
    pred   = result.get("prediction", {})
    sp     = result.get("species", {})
    rule   = pred.get("rule_based_risk", {})
    coords = result.get("coordinates", {})
    now    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    risk_label = pred.get("risk_label", "Low")
    bloom_det  = pred.get("bloom_detected", False)
    oil_det    = pred.get("oil_spill_detected", False)
    temp       = env.get("temperature", "N/A")
    chl        = env.get("chlorophyll", "N/A")
    turb       = env.get("turbidity", "N/A")
    risk_conf  = pred.get("risk_confidence", 0) or 0
    bloom_conf = pred.get("bloom_confidence", 0) or 0

    risk_icon  = "🔴" if risk_label == "High" else "🟢"
    bloom_icon = "🟠" if bloom_det else "🟢"
    oil_icon   = "🔴" if oil_det   else "🟢"

    # ── Species sections ──────────────────────────────────────────────────────
    def _sp_rows(key, label):
        items = sp.get(key, [])
        if not items:
            return ""
        lines = f"\n### {label} ({len(items)} species)\n"
        for s in items[:8]:
            harm = f" — ⚠ {'; '.join(s['harm_reasons'])}" if s.get("harm_reasons") else ""
            cn   = s.get('common_name') or 'N/A'
            lines += f"- **{s['name']}** (*{cn}*){harm}\n"
        return lines

    threatened_section = (
        _sp_rows("critically_endangered", "🚨 Critically Endangered") +
        _sp_rows("endangered",            "⚠️  Endangered") +
        _sp_rows("vulnerable",            "⚡ Vulnerable")
    ) or "\n*No threatened species detected in this region.*\n"

    harmed_list = sp.get("currently_harmed", [])
    harmed_section = "\n### 🩹 Currently Harmed Species\n"
    if harmed_list:
        for s in harmed_list[:8]:
            reasons = "; ".join(s.get("harm_reasons", []))
            harmed_section += f"- **{s['name']}**: {reasons}\n"
    else:
        harmed_section += "*No species are currently harmed under present conditions.*\n"

    # ── Conservation measures ─────────────────────────────────────────────────
    conservation_section = ""
    if sp.get("threatened_count", 0) > 0 or harmed_list:
        conservation_section = """
---

## 🌿 Conservation Action Plan

### 🚨 Immediate Actions (0–72 Hours)
- **Declare temporary no-take zones** around the affected region for critically endangered species
- **Alert local fisheries boards** and maritime patrol about harmed species populations
- **Deploy monitoring buoys** to track water quality and wildlife movement in real time
- **Block destructive fishing** — ban trawling and dynamite fishing in the area immediately

### 📅 Short-Term (1–4 Weeks)
- Conduct **underwater biodiversity surveys** to assess species density and health
- **Coordinate with IUCN / WWF** for rapid-response marine conservation teams
- Reduce **boat traffic and noise pollution** — acoustic stress worsens survival rates
- **Establish temporary exclusion zones** for nesting, spawning, and feeding grounds

### 🌏 Long-Term Measures
- Establish or expand **Marine Protected Areas (MPAs)** around this zone
- Implement **seasonal fishing bans** during breeding periods of threatened species
- Fund **coral reef and mangrove restoration** programs if habitats are degraded
- Launch **satellite tagging programs** for charismatic threatened species
- Engage **local fishing communities** in co-managed conservation and alternative livelihood programs
"""

    # ── Oil spill response ────────────────────────────────────────────────────
    oil_section = ""
    if oil_det:
        oil_section = f"""
---

## 🛢️ Oil Spill Emergency Response

> **⚠️ OIL SPILL DETECTED** — SAR Backscatter: {pred.get('sar_value', 'N/A')} dB
> Immediate coordinated response is required.

### Phase 1: Emergency Response (0–24 Hours)
1. **Notify Coast Guard** and National Maritime Disaster Authority immediately
2. **Deploy containment booms** around the spill perimeter to halt spread
3. **Locate and stop the source** — inspect nearby vessels, pipelines, rigs
4. **Evacuate sensitive areas** — clear aquafarms, turtle nesting beaches, fishing zones
5. **Alert coastal communities** dependent on the ocean for drinking water or livelihood

### Phase 2: Cleanup Operations (Days 1–7)
- Deploy **oil skimmer vessels** to mechanically skim surface oil
- Apply **oleophilic sorbents** (peat moss, synthetic pads) for scattered surface patches
- Use **chemical dispersants** only if approved — reduces visible slick but has subsurface impact
- **Avoid high-pressure washing** of shorelines — forces oil into sediments
- Rescue and transfer **oil-contaminated wildlife** (seabirds, sea turtles) to rehabilitation centres

### Phase 3: Ocean Recovery (Months 1–6)
- Monitor **dissolved oxygen** daily — decomposing oil creates hypoxic dead zones
- **Ban seafood harvesting** until toxicity tests confirm safety — bioaccumulation risk
- Restore shorelines through **mangrove replanting** and salt marsh vegetation
- File **MARPOL incident reports** with IMO for international coordination
- Apply **bioremediation** using oil-degrading bacteria (*Alcanivorax*, *Marinobacter*) in sediments
"""

    # ── Algal bloom advisory ──────────────────────────────────────────────────
    bloom_section = ""
    if bloom_det:
        bloom_section = f"""
---

## 🌿 Algal Bloom Advisory & Mitigation

> **⚠️ BLOOM DETECTED** — Chlorophyll-a: {chl} mg/m³ (threshold: 5.0 mg/m³)
> Active phytoplankton bloom posing risk to humans and marine life.

### Immediate Precautions
- **Ban shellfish harvesting** — bivalves concentrate dangerous algal toxins within hours
- **Close beaches and water bodies** — issue public health advisory against swimming
- **Test for HAB toxins** (microcystin, saxitoxin, domoic acid) at nearest certified lab
- **Halt aquaculture operations** — oxygen depletion from bloom can cause mass fish kills

### Mitigation Actions
- **Curb agricultural runoff** — enforce fertiliser discharge limits into rivers feeding this basin
- Deploy **algae harvesting nets** for small, localized surface blooms
- **Increase water circulation** with aerators in enclosed bays and marinas
- Apply **modified clay flocculation** to sink bloom biomass in critical harbor areas

### Recovery Indicators
- Sample Chl-a **weekly** until it falls below 2.0 mg/m³
- Monitor **dissolved oxygen** (below 4 mg/L is hypoxic — fish kill risk)
- Track **pH** — blooms cause alkaline spikes by day, acidification by night
"""

    # ── Ecosystem risk advisory ───────────────────────────────────────────────
    risk_section = ""
    if risk_label == "High":
        factors = ", ".join(rule.get("contributing_factors", [])) or "Multiple environmental stressors"
        risk_section = f"""
---

## ⚠️ Ecosystem Risk Advisory

> **HIGH RISK** status detected with **{round(risk_conf * 100, 1)}%** model confidence.
> Primary drivers: *{factors}*

### Recommended Response
- **Declare precautionary fishing closures** for 2–4 weeks in the affected zone
- Request **daily MODIS / Sentinel satellite passes** for continuous monitoring
- Brief **maritime patrol and coast guard** vessels to report surface anomalies
- Activate **coastal early warning systems** for fishing communities
- Coordinate with **INCOIS & NOAA** for real-time ocean state bulletins and forecast support
"""

    # ── Build final report ────────────────────────────────────────────────────
    temp_status = "⚠️ Thermal Stress (>30°C)" if isinstance(temp, (int,float)) and temp > 30 else "✅ Normal"
    chl_status  = ("🔴 Bloom-level (>5)" if isinstance(chl, (int,float)) and chl>5
                   else ("🟠 Elevated (2–5)" if isinstance(chl, (int,float)) and chl>2 else "✅ Normal (<2)"))
    turb_status = "⚠️ High (>0.5)" if isinstance(turb, (int,float)) and turb > 0.5 else "✅ Normal"

    rec_lines = []
    if oil_det:   rec_lines.append("- 🔴 **URGENT:** Contact coast guard — initiate oil spill containment immediately")
    if bloom_det: rec_lines.append("- 🟠 **HIGH:** Issue public health advisory and ban shellfish harvesting")
    if risk_label == "High": rec_lines.append("- 🔴 **HIGH:** Declare precautionary fishing closure in affected zone")
    if sp.get("harmed_count", 0) > 0:
        rec_lines.append(f"- 🐟 **ACTION:** Engage IUCN rapid response for {sp['harmed_count']} harmed species")
    rec_lines += [
        "- 📡 **MONITOR:** Continue satellite monitoring every 24–48 hours",
        "- 📊 **REPORT:** Share findings with INCOIS, Fisheries Dept., and maritime authority",
        "- 🌐 **COORDINATE:** Submit incident data to Global Ocean Observing System (GOOS)",
    ]

    report = f"""# 🌊 OceanSense — Ocean Health Report

**Location:** {location}
**Coordinates:** {coords.get('lat', 'N/A')}°N, {coords.get('lon', 'N/A')}°E
**Generated:** {now}
**Data Source:** {env.get('source', 'N/A')}
**Date Range:** {env.get('date_range', 'N/A')}

---

## 📊 Executive Summary

| Indicator | Status | Value |
|---|---|---|
| Ecosystem Risk | {risk_icon} **{risk_label}** | Confidence: {round(risk_conf*100,1)}% · Rule score: {rule.get('risk_score','N/A')}/1.0 |
| Algal Bloom | {bloom_icon} **{'DETECTED' if bloom_det else 'Clear'}** | Confidence: {round(bloom_conf*100,1)}% · Chl-a: {chl} mg/m³ |
| Oil Spill | {oil_icon} **{'⚠️ DETECTED' if oil_det else 'Not Detected'}** | SAR backscatter: {pred.get('sar_value','N/A')} dB |
| Sea Surface Temp | {'🌡️ Elevated' if isinstance(temp,(int,float)) and temp>30 else '🌡️ Normal'} | {temp} °C |
| Turbidity | {'⚠️ Elevated' if isinstance(turb,(int,float)) and turb>0.5 else '✅ Normal'} | {turb} NTU |
| Marine Species | 🐟 {sp.get('threatened_count',0)} threatened | {sp.get('harmed_count',0)} currently harmed |

---

## 🌡️ Environmental Parameters

| Parameter | Measured Value | Status |
|---|---|---|
| Sea Surface Temperature | {temp} °C | {temp_status} |
| Chlorophyll-a | {chl} mg/m³ | {chl_status} |
| Turbidity | {turb} NTU | {turb_status} |

---

## 🤖 ML Model Predictions

| Model | Prediction | Confidence |
|---|---|---|
| Ecosystem Risk (Random Forest) | {risk_icon} {risk_label} | {round(risk_conf*100,1)}% |
| Algal Bloom (XGBoost) | {bloom_icon} {'Detected' if bloom_det else 'Not Detected'} | {round(bloom_conf*100,1)}% |
| Oil Spill (ML + SAR Sentinel-1) | {oil_icon} {'⚠️ DETECTED' if oil_det else 'Not Detected'} | {'N/A' if not pred.get('oil_spill_confidence') else f"{round(pred['oil_spill_confidence']*100,1)}%"} |

**Rule-Based Assessment** — Score: {rule.get('risk_score','N/A')}/1.0 · Level: {rule.get('risk_label','N/A')}
Contributing factors: *{', '.join(rule.get('contributing_factors',[])) or 'None detected'}*

---

## 🐠 Marine Species Assessment

- **Total Species Found:** {sp.get('total_found', 0)}
- **Threatened Species:** {sp.get('threatened_count', 0)}
- **Currently Harmed:** {sp.get('harmed_count', 0)}
{threatened_section}
{harmed_section}
{risk_section}
{bloom_section}
{oil_section}
{conservation_section}
---

## 📋 Recommendations & Action Summary

{chr(10).join(rec_lines)}

---

*Report generated by **OceanSense Ocean Intelligence Platform***
*Data: NASA MODIS · NOAA OISST · Copernicus Sentinel-1 · GBIF · IUCN Red List*
*Emergency contacts: INCOIS +91-40-23895001 | IMO incident reporting: www.imo.org*
"""
    return {"location": location, "generated_at": now, "report": report, "data": result}


# ── Scheduler ──────────────────────────────────────────────────────────────────
@app.get("/scheduler/status")
def scheduler_status():
    if not os.path.exists(SCHEDULER_RESULTS_FILE):
        return {"status": "no_runs_yet", "results": {}}
    try:
        with open(SCHEDULER_RESULTS_FILE, "r") as f:
            results = json.load(f)
        return {"status": "ok", "total_locations": len(results), "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read scheduler results: {e}")


@app.get("/scheduler/history")
def scheduler_history(lines: int = 50):
    history_file = "outputs/scheduler_history.log"
    if not os.path.exists(history_file):
        return {"status": "no_history_yet", "lines": []}
    try:
        with open(history_file, "r") as f:
            all_lines = f.readlines()
        return {"status": "ok", "total_lines": len(all_lines),
                "lines": [l.rstrip() for l in all_lines[-lines:]]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read history: {e}")


@app.post("/scheduler/run")
def scheduler_run_now():
    global _scheduler_running
    if _scheduler_running:
        return {"status": "already_running", "message": "A scheduler run is already in progress"}

    def _run():
        global _scheduler_running, _scheduler_progress
        _scheduler_running = True
        _scheduler_progress = "Starting..."
        try:
            from scheduler.schedule_pipeline import run_all_locations
            def _prog(s):
                global _scheduler_progress
                _scheduler_progress = s
            run_all_locations(progress_callback=_prog)
            asyncio.run(_broadcast_scheduler_update())
        except Exception as e:
            logger.error(f"Scheduler run failed: {e}")
        finally:
            _scheduler_running = False
            _scheduler_progress = ""

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"status": "started", "message": "Scheduler run started in background. Refresh monitor in ~30 seconds."}


@app.get("/scheduler/running")
def scheduler_is_running():
    return {"running": _scheduler_running, "progress": _scheduler_progress}


async def _broadcast_scheduler_update():
    """Push latest scheduler results to all connected WebSocket clients."""
    if not os.path.exists(SCHEDULER_RESULTS_FILE):
        return
    try:
        with open(SCHEDULER_RESULTS_FILE) as f:
            results = json.load(f)
        await ws_manager.broadcast({"type": "scheduler_update", "results": results,
                                    "timestamp": datetime.now(timezone.utc).isoformat()})
    except Exception:
        pass


# ── Trends ─────────────────────────────────────────────────────────────────────
@app.get("/trends")
def get_trends(location: str, days: int = 90):
    from services.location_service import get_coordinates
    from services.trend_service import get_historical_trends

    cache_key = f"trends:{location.lower()}:{days}"
    cached = _cache_get(cache_key)
    if cached:
        _metrics["cache_hits"] += 1
        return cached

    _metrics["cache_misses"] += 1
    lat, lon = get_coordinates(location)
    if lat is None:
        raise HTTPException(status_code=404, detail=f"Could not geocode: {location}")
    try:
        data = get_historical_trends(lat, lon, days=days)
        data["location_name"] = location
        _cache_set(cache_key, data, ttl=600)   # trends cached 10 min
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Alerts ─────────────────────────────────────────────────────────────────────
@app.get("/pollution/history")
def pollution_history(limit: int = 50):
    from services.pollution_service import get_pollution_history
    return {"events": get_pollution_history(limit)}


@app.get("/alerts/history")
def alerts_history():
    if not os.path.exists(ALERT_HISTORY_FILE):
        return {"alerts": []}
    try:
        with open(ALERT_HISTORY_FILE) as f:
            return {"alerts": json.load(f)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/alerts/unread-count")
def alerts_unread_count():
    """Returns count of alerts in the last 24 hours — used for notification badge."""
    if not os.path.exists(ALERT_HISTORY_FILE):
        return {"count": 0}
    try:
        with open(ALERT_HISTORY_FILE) as f:
            alerts = json.load(f)
        cutoff = datetime.now(timezone.utc).timestamp() - 86400
        recent = [
            a for a in alerts
            if a.get("timestamp") and
               datetime.fromisoformat(a["timestamp"].replace("Z","")).timestamp() > cutoff
        ]
        return {"count": len(recent)}
    except Exception:
        return {"count": 0}


# ── Locations ──────────────────────────────────────────────────────────────────
@app.get("/locations")
def get_locations():
    default = ["Arabian Sea", "Gulf of Mexico", "Bay of Bengal", "Persian Gulf", "Baltic Sea"]
    if os.path.exists(CUSTOM_LOCATIONS_FILE):
        try:
            with open(CUSTOM_LOCATIONS_FILE) as f:
                return {"locations": json.load(f)}
        except Exception:
            pass
    return {"locations": default}


class LocationsBody(BaseModel):
    locations: list[str]


@app.post("/locations")
def save_locations(body: LocationsBody):
    locs = [l.strip() for l in body.locations if l.strip()]
    if not locs:
        raise HTTPException(status_code=400, detail="At least one location required")
    os.makedirs("outputs", exist_ok=True)
    with open(CUSTOM_LOCATIONS_FILE, "w") as f:
        json.dump(locs, f)
    os.environ["MONITORED_LOCATIONS"] = ",".join(locs)
    return {"status": "saved", "locations": locs}


# ── Metrics endpoint ───────────────────────────────────────────────────────────
@app.get("/metrics")
def get_metrics():
    """
    Prometheus-compatible plain-text metrics + JSON summary.
    Tracks request counts, cache performance, errors, uptime.
    """
    uptime_s = (datetime.now(timezone.utc) - datetime.fromisoformat(_metrics["started_at"])).total_seconds()
    cache_total = _metrics["cache_hits"] + _metrics["cache_misses"]
    hit_rate = round(_metrics["cache_hits"] / cache_total * 100, 1) if cache_total else 0

    return {
        **_metrics,
        "uptime_seconds":    round(uptime_s),
        "cache_hit_rate_pct": hit_rate,
        "active_ws_clients": len(ws_manager.active),
        "cache_entries":     len(_cache),
        "rate_store_ips":    len(_rate_store),
    }


# ── Model drift detection ──────────────────────────────────────────────────────
@app.get("/drift")
def check_drift(location: str):
    """
    Compares current live environmental values against the training data distribution.
    Returns a drift score and flags features that are out-of-distribution.
    """
    from services.location_service import get_coordinates
    from services.environment_service import get_environment_data
    import numpy as np

    # Training distribution stats (from train_improved_models.py synthetic data)
    TRAIN_STATS = {
        "temperature":  {"mean": 26.5, "std": 4.2,  "min": 15.0, "max": 35.0},
        "chlorophyll":  {"mean": 2.8,  "std": 2.6,  "min": 0.1,  "max": 15.0},
        "turbidity":    {"mean": 0.28, "std": 0.18, "min": 0.05, "max": 0.9},
    }

    lat, lon = get_coordinates(location)
    if lat is None:
        raise HTTPException(status_code=404, detail=f"Could not geocode: {location}")

    env = get_environment_data(lat, lon)
    if "error" in env:
        raise HTTPException(status_code=500, detail=env["error"])

    features = {
        "temperature": env.get("temperature"),
        "chlorophyll": env.get("chlorophyll"),
        "turbidity":   env.get("turbidity"),
    }

    drift_flags = []
    z_scores    = {}
    for feat, val in features.items():
        if val is None:
            continue
        stats = TRAIN_STATS[feat]
        z = abs((val - stats["mean"]) / (stats["std"] + 1e-9))
        z_scores[feat] = round(z, 2)
        if z > 2.5:
            drift_flags.append({
                "feature":    feat,
                "live_value": val,
                "train_mean": stats["mean"],
                "train_std":  stats["std"],
                "z_score":    round(z, 2),
                "severity":   "high" if z > 3.5 else "moderate"
            })

    overall_drift = max(z_scores.values()) if z_scores else 0
    return {
        "location":      location,
        "live_values":   features,
        "z_scores":      z_scores,
        "drift_flags":   drift_flags,
        "drift_detected": len(drift_flags) > 0,
        "overall_drift_score": round(overall_drift, 2),
        "recommendation": (
            "Model retraining recommended — live data is significantly out of training distribution."
            if overall_drift > 3.5 else
            "Moderate drift detected — monitor closely."
            if overall_drift > 2.5 else
            "No significant drift detected. Model predictions are reliable."
        )
    }


# ── WebSocket — live alerts push ───────────────────────────────────────────────
@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    """
    WebSocket endpoint. Clients connect here to receive real-time push
    notifications when the scheduler detects high-risk conditions.
    """
    await ws_manager.connect(websocket)
    try:
        # Send current alert count immediately on connect
        count_data = alerts_unread_count()
        await websocket.send_json({"type": "init", **count_data})
        # Keep alive — wait for disconnect
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# ── Health ─────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


# ── Alert endpoints ────────────────────────────────────────────────────────────
class TestAlertBody(BaseModel):
    email: str
    name: str | None = "Test User"


@app.post("/alerts/test")
def test_alert(body: TestAlertBody):
    from services.alert_service import send_test_alert
    result = send_test_alert(to_email=body.email.strip(), user_name=body.name or "Test User")
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@app.post("/alerts/trigger")
def trigger_alert(location: str):
    from services.alert_service import send_alert
    result = run_prediction_pipeline(location.strip())
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    send_alert(
        location=location,
        prediction=result.get("prediction", {}),
        environment=result.get("environment", {}),
        species=result.get("species", {})
    )
    return {
        "status":     "alert_triggered",
        "location":   location,
        "risk_label": result.get("prediction", {}).get("risk_label"),
        "bloom":      result.get("prediction", {}).get("bloom_detected"),
        "oil_spill":  result.get("prediction", {}).get("oil_spill_detected"),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=False)
