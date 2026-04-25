# 🌊 AquaGuard — Ocean Health Intelligence Platform

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-2.0-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![TensorFlow](https://img.shields.io/badge/TensorFlow-CNN-FF6F00?style=for-the-badge&logo=tensorflow&logoColor=white)
![Google Earth Engine](https://img.shields.io/badge/GEE-Satellite-34A853?style=for-the-badge&logo=google&logoColor=white)
[![Resume](https://img.shields.io/badge/📄_Resume-View-0A66C2?style=for-the-badge)](https://YOUR_RESUME_LINK_HERE)

**Real-time ocean health monitoring using satellite imagery, ML models, and an AI agent.**

</div>

---

## 📌 About

AquaGuard is an end-to-end ocean health intelligence platform that monitors global ocean locations in real time. It uses satellite data from NASA MODIS, Copernicus Sentinel-1, and Google Earth Engine to detect:

- 🌿 **Algal Blooms** — XGBoost classifier on chlorophyll-a levels
- 🛢️ **Oil Spills** — CNN model on SAR Sentinel-1 radar imagery
- ⚠️ **Ecosystem Risk** — Random Forest risk model using multi-variate features
- 🐠 **Marine Species Impact** — GBIF + IUCN Red List species harm analysis
- 🤖 **AI Ocean Agent** — Gemini-powered conversational assistant (supports English, Hindi, Marathi)

---

## 🖥️ Features

| Feature | Description |
|---|---|
| 🔍 Location Search | Search any global ocean location for real-time health data |
| 📊 Live Dashboard | Interactive frontend with charts, alerts, and risk panels |
| 🤖 AI Agent | Ask questions in English, Hindi, or Marathi |
| 📋 Health Reports | Downloadable markdown reports with conservation action plans |
| 📡 Scheduler | Auto-monitors configured ocean zones every 24 hours |
| 🔔 Real-time Alerts | WebSocket-powered push alerts for high-risk events |
| 📈 Trend Analysis | 90-day historical trend charts for temperature & chlorophyll |
| 🚦 Model Drift Detection | Live feature drift scoring vs. training distribution |

---

## 🛠️ Tech Stack

**Backend**
- FastAPI + Uvicorn (REST API + WebSockets)
- Python 3.10+
- Google Earth Engine (satellite data)

**Machine Learning**
- TensorFlow / Keras (Oil Spill CNN)
- Scikit-learn Random Forest (Ecosystem Risk)
- XGBoost (Algal Bloom Detection)
- LightGBM + scikit-learn LOF (Anomaly)
- SHAP (model explainability)

**Data Sources**
- NASA MODIS (SST, Chlorophyll-a)
- Copernicus Sentinel-1 (SAR radar)
- GBIF (species occurrence)
- IUCN Red List API (conservation status)
- Open-Meteo (historical oceanographic data)

**Frontend**
- Vanilla HTML + CSS + JavaScript
- WebSocket live updates

---

## 🚀 Getting Started

### 1. Clone the repository
```bash
git clone https://github.com/aaryasachinvarsolkar/aquaguard.git
cd aquaguard
```

### 2. Create a virtual environment
```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up environment variables
```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

Required keys in `.env`:
```env
GOOGLE_API_KEY=your_google_api_key
GEMINI_API_KEY=your_gemini_api_key
RESEND_API_KEY=your_resend_api_key
```

### 5. Train ML models (first time only)
```bash
python models/train_risk_model.py
python models/train_bloom_model.py
python models/train_oil_spill_model.py
python models/train_anomaly_model.py
```

### 6. Start the backend
```bash
.\start_backend.ps1
# or manually:
uvicorn backend.app:app --reload --port 8000
```

### 7. Open the frontend
Open `frontend/index.html` in your browser, or serve it:
```bash
cd frontend
python -m http.server 3000
```

Then go to: `http://localhost:3000`

---

## 📁 Project Structure

```
aquaguard/
├── backend/          # FastAPI app (app.py - main API)
├── frontend/         # HTML/CSS/JS dashboard
├── agents/           # Gemini AI ocean agent
├── services/         # Data fetch services (environment, species, oil spill, etc.)
├── pipeline/         # ML prediction pipeline
├── models/           # Trained ML models + training scripts
├── scripts/          # Data fetching, preprocessing, evaluation scripts
├── scheduler/        # Auto-monitoring scheduler
├── configs/          # YAML configuration
├── utils/            # Logging, config loader helpers
├── tests/            # Unit tests
├── requirements.txt  # Python dependencies
└── .env.example      # Environment variables template
```

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/search?location=` | Run full prediction pipeline for a location |
| GET | `/report?location=` | Generate downloadable ocean health report |
| POST | `/agent` | Query the AI ocean agent |
| GET | `/trends?location=&days=90` | 90-day historical trend data |
| GET | `/alerts/history` | Alert event history |
| GET | `/metrics` | API performance metrics |
| GET | `/drift?location=` | Model drift detection |
| WS | `/ws/alerts` | Real-time WebSocket alerts |

---

## ⚙️ Environment Variables

| Variable | Description |
|---|---|
| `GOOGLE_API_KEY` | Google Earth Engine + Generative AI |
| `GEMINI_API_KEY` | Gemini AI agent |
| `RESEND_API_KEY` | Email alert notifications |

> **Never commit your `.env` file.** Use `.env.example` as a template.

---

## 🧑‍💻 Author

**Aarya Sachin Varsolkar**

[![Resume](https://img.shields.io/badge/📄_Resume-View-0A66C2?style=for-the-badge)](https://YOUR_RESUME_LINK_HERE)
[![GitHub](https://img.shields.io/badge/GitHub-aaryasachinvarsolkar-181717?style=for-the-badge&logo=github)](https://github.com/aaryasachinvarsolkar)

---

## 📄 License

This project is for educational and research purposes.

---

*Data sources: NASA MODIS · NOAA OISST · Copernicus Sentinel-1 · GBIF · IUCN Red List*
