# FastAPI App

Minimal FastAPI scaffold with health check and echo endpoint.

## Run

```bash
pip install -r requirements.txt
python main.py
```

## Endpoints

| Method | Path      | Description                    |
|--------|-----------|--------------------------------|
| GET    | `/health` | Health check                   |
| POST   | `/echo`   | Echo back a message            |

## Example

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/echo -H "Content-Type: application/json" -d '{"message": "hello"}'
```
