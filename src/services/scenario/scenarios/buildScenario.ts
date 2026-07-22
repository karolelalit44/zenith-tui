import type { Scenario } from '../../../types/scenario';
import { createScenario, type ScenarioTemplate } from '../templateLoader';

const template: ScenarioTemplate = {
  mode: 'build',
  events: [
    {
      kind: 'thinking',
      thoughts: [
        { text: 'Parsing workspace AST & inspecting pyproject.toml / requirements.txt dependencies...', delay: 250 },
        {
          text: 'Evaluating FastAPI async lifespan context, Pydantic v2 BaseModel schemas, and SQLAlchemy 2.0 ORM session scoping',
          delay: 300,
        },
        {
          text: 'Architecting JWT bearer token authentication, bcrypt password hashing, and CORS middleware security policy',
          delay: 350,
        },
        {
          text: 'Formulating Pytest async test fixture isolation, httpx AsyncClient suites, and mypy strict static type checks',
          delay: 300,
        },
      ],
      duration: 1500,
    },
    {
      kind: 'terminal',
      command:
        'python -m venv .venv && source .venv/bin/activate && pip install fastapi uvicorn pydantic pytest httpx mypy',
      output: [
        'Creating virtual environment in .venv...',
        'Installing packages: fastapi (0.115.0), uvicorn (0.30.0), pydantic (2.9.0), pytest (8.3.0)...',
        'Successfully installed 18 dependencies in 1.84s',
      ],
      duration: 1800,
    },
    {
      kind: 'file_create',
      filePath: 'backend/app/schemas.py',
      directory: 'backend/app/',
      language: 'python',
      lines: [
        { text: 'from pydantic import BaseModel, EmailStr, Field', type: 'add' },
        { text: 'from datetime import datetime', type: 'add' },
        { text: 'from typing import Optional', type: 'add' },
        { text: '', type: 'add' },
        { text: 'class UserBase(BaseModel):', type: 'add' },
        { text: '    email: EmailStr', type: 'add' },
        { text: '    is_active: bool = True', type: 'add' },
        { text: '    role: str = Field(default="developer", pattern="^(admin|developer|auditor)$")', type: 'add' },
        { text: '', type: 'add' },
        { text: 'class UserCreate(UserBase):', type: 'add' },
        {
          text: '    password: str = Field(..., min_length=8, description="Minimum 8 characters with high entropy")',
          type: 'add',
        },
        { text: '', type: 'add' },
        { text: 'class UserResponse(UserBase):', type: 'add' },
        { text: '    id: int', type: 'add' },
        { text: '    created_at: datetime', type: 'add' },
        { text: '', type: 'add' },
        { text: '    class Config:', type: 'add' },
        { text: '        from_attributes = True', type: 'add' },
      ],
    },
    {
      kind: 'file_create',
      filePath: 'backend/app/main.py',
      directory: 'backend/app/',
      language: 'python',
      lines: [
        { text: 'from contextlib import asynccontextmanager', type: 'add' },
        { text: 'from fastapi import FastAPI, HTTPException, status, Depends', type: 'add' },
        { text: 'from fastapi.middleware.cors import CORSMiddleware', type: 'add' },
        { text: 'from app.schemas import UserCreate, UserResponse', type: 'add' },
        { text: 'from datetime import datetime, timezone', type: 'add' },
        { text: '', type: 'add' },
        { text: 'db_users = {}', type: 'add' },
        { text: '', type: 'add' },
        { text: '@asynccontextmanager', type: 'add' },
        { text: 'async def lifespan(app: FastAPI):', type: 'add' },
        { text: '    # Startup: Database connection pool & cache warm-up', type: 'add' },
        { text: '    yield', type: 'add' },
        { text: '    # Shutdown: Release connection resources cleanly', type: 'add' },
        { text: '', type: 'add' },
        { text: 'app = FastAPI(title="Zenith Enterprise API", version="1.0.0", lifespan=lifespan)', type: 'add' },
        { text: '', type: 'add' },
        { text: 'app.add_middleware(', type: 'add' },
        { text: '    CORSMiddleware,', type: 'add' },
        { text: '    allow_origins=["*"],', type: 'add' },
        { text: '    allow_credentials=True,', type: 'add' },
        { text: '    allow_methods=["*"],', type: 'add' },
        { text: '    allow_headers=["*"],', type: 'add' },
        { text: ')', type: 'add' },
        { text: '', type: 'add' },
        {
          text: '@app.post("/api/v1/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)',
          type: 'add',
        },
        { text: 'async def create_user(user: UserCreate):', type: 'add' },
        { text: '    if user.email in db_users:', type: 'add' },
        {
          text: '        raise HTTPException(status_code=400, detail="Email address already registered")',
          type: 'add',
        },
        { text: '    user_id = len(db_users) + 1', type: 'add' },
        {
          text: '    record = {**user.model_dump(), "id": user_id, "created_at": datetime.now(timezone.utc)}',
          type: 'add',
        },
        { text: '    db_users[user.email] = record', type: 'add' },
        { text: '    return record', type: 'add' },
      ],
    },
    {
      kind: 'build_step',
      step: 'Mypy Strict Static Type Analysis ($ mypy backend/app)',
      status: 'success',
      duration: 650,
      output: ['Success: no issues found in 2 source files.'],
    },
    {
      kind: 'test_execution',
      command: 'pytest backend/tests/test_users.py -vv',
      framework: 'Pytest 8.3.0 (asyncio)',
      summary: { total: 3, passed: 3, failed: 0, skipped: 0 },
      results: [
        { name: 'test_create_user_success (POST /api/v1/users -> 201 Created)', status: 'pass', duration: 32 },
        { name: 'test_create_duplicate_user_raises_400', status: 'pass', duration: 18 },
        { name: 'test_user_schema_pydantic_validation', status: 'pass', duration: 12 },
      ],
    },
    {
      kind: 'summary',
      title: 'Enterprise FastAPI Microservice Created & Verified',
      description:
        'Built FastAPI REST service with Pydantic v2 schemas, async lifespan manager, CORS middleware, mypy static analysis, and Pytest coverage.',
      filesCreated: ['backend/app/schemas.py', 'backend/app/main.py'],
      commandsExecuted: [
        'python -m venv .venv',
        'pip install fastapi uvicorn pydantic pytest httpx mypy',
        'mypy backend/app',
        'pytest backend/tests/test_users.py',
      ],
      verified: [
        'FastAPI Async Endpoint & CORS Middleware',
        'Pydantic v2 Field Validation & OpenAPI 3.1 Spec',
        'Mypy Strict Static Type Compliance',
        'Pytest Async Unit Test Suite (3 passed)',
      ],
    },
  ],
};

export const buildScenario = (prompt: string): Scenario => createScenario(prompt, template);
