# RGMB-Hub API

A lightweight FastAPI service featuring health check and welcome endpoints, fully containerized with Docker and Docker Compose.

## Project Structure

```text
rgmb-hub/
├── main.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Endpoints

- `GET /` - Welcome screen / bootstrap home screen.
- `GET /health` - Health check endpoint returning service status.

## Running locally (Python)

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the application:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

## Running with Docker / Docker Compose

1. Build and run using Docker Compose:
   ```bash
   docker-compose up --build
   ```
2. Access the API at `http://localhost:8000`.
