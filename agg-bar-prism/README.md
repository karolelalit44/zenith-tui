# Agg-Bar-Prism FastAPI Data Pipeline API

A containerized FastAPI application with Bronze, Silver, and Gold data layers built on CSV base data with automated data manipulation triggers.

## Project Structure
- `agg-bar-prism/main.py`: FastAPI application with health check and bronze, silver, gold endpoints.
- `agg-bar-prism/data_generator.py`: Generates the base raw CSV dataset.
- `agg-bar-prism/requirements.txt`: Python dependencies (`fastapi`, `uvicorn`, `pandas`).
- `agg-bar-prism/Dockerfile`: Docker container specification.

---

## Getting Started

### 1. Run Locally (Python)
Navigate to the application folder and install dependencies:
```bash
cd agg-bar-prism
pip install -r requirements.txt
python main.py
```
The server will start at `http://localhost:8000`.

### 2. Run with Docker
Build the Docker image:
```bash
docker build -t agg-bar-prism ./agg-bar-prism
```

Run the Docker container:
```bash
docker run -p 8000:8000 agg-bar-prism
```

---

## API Endpoints

- **Health Check**: `GET /health`
  - Returns service status, timestamp, and checks if base raw data exists.
  
- **Bronze Data Layer**: `GET /bronze`
  - Triggers ingestion manipulation: reads raw CSV base data, cleans missing values, standardizes column names, and adds ingest timestamps.

- **Silver Data Layer**: `GET /silver`
  - Triggers transformation manipulation: aggregates sales by category/region, calculates total revenue, and filters validated records.

- **Gold Data Layer**: `GET /gold`
  - Triggers business-level analytics: computes top performing categories, profit margins, and summary metrics ready for dashboard consumption.

---

## Interactive Documentation
Once running, visit Swagger UI at:
`http://localhost:8000/docs`
