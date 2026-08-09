from fastapi import FastAPI

app = FastAPI(title="RGMB Hub", version="1.0.0")

@app.get("/")
def home():
    return {"message": "Welcome to RGMB Hub API"}

@app.get("/health")
def health():
    return {"status": "healthy"}
