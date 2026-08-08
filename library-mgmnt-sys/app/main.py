from fastapi import FastAPI
from app.routes import book, account, user
from app.database import engine
from app import models

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Library Management System",
    description="A simple library management system API",
    version="1.0.0"
)

# Include routers
app.include_router(book.router)
app.include_router(account.router)
app.include_router(user.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to Library Management System API", "version": "1.0.0"}