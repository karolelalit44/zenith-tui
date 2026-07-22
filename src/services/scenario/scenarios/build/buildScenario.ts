import { Scenario } from '../../../../types/scenario';

let idCounter = 0;
const uid = () => `build_${Date.now()}_${++idCounter}`;

export const buildScenario = (prompt: string): Scenario => ({
  id: `build_${Date.now()}`,
  mode: 'build',
  prompt,
  events: [
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'Analyzing project workspace & requirements', delay: 300 },
        { text: 'Inspecting existing file structure and dependencies', delay: 350 },
        { text: 'Designing FastAPI application module structure', delay: 400 },
      ],
      duration: 1500,
    },
    {
      kind: 'terminal',
      id: uid(),
      command: 'git status',
      output: [
        'On branch main',
        'Your branch is up to date with "origin/main".',
        'nothing to commit, working tree clean',
      ],
      duration: 500,
    },
    {
      kind: 'file_create',
      id: uid(),
      filePath: 'backend/main.py',
      directory: 'backend/',
      language: 'python',
      lines: [
        { text: 'from fastapi import FastAPI, HTTPException', type: 'add' },
        { text: 'from backend.app.api.users import router as user_router', type: 'add' },
        { text: '', type: 'add' },
        { text: 'app = FastAPI(title="Zenith Backend Engine", version="1.0.0")', type: 'add' },
        { text: 'app.include_router(user_router, prefix="/api/v1/users", tags=["Users"])', type: 'add' },
        { text: '', type: 'add' },
        { text: '@app.get("/health")', type: 'add' },
        { text: 'async function health_check():', type: 'add' },
        { text: '    return {"status": "ok", "service": "zenith-backend"}', type: 'add' },
      ],
    },
    {
      kind: 'file_create',
      id: uid(),
      filePath: 'backend/app/models.py',
      directory: 'backend/app/',
      language: 'python',
      lines: [
        { text: 'from pydantic import BaseModel, EmailStr', type: 'add' },
        { text: 'from typing import Optional', type: 'add' },
        { text: '', type: 'add' },
        { text: 'class UserBase(BaseModel):', type: 'add' },
        { text: '    username: str', type: 'add' },
        { text: '    email: EmailStr', type: 'add' },
        { text: '    is_active: bool = True', type: 'add' },
        { text: '', type: 'add' },
        { text: 'class UserCreate(UserBase):', type: 'add' },
        { text: '    password: str', type: 'add' },
        { text: '', type: 'add' },
        { text: 'class UserResponse(UserBase):', type: 'add' },
        { text: '    id: int', type: 'add' },
      ],
    },
    {
      kind: 'test_execution',
      id: uid(),
      command: 'pytest backend/tests/test_users.py',
      framework: 'Pytest 8.1',
      results: [
        { name: 'test_create_user_success', status: 'pass', duration: 84 },
        { name: 'test_get_user_by_id', status: 'pass', duration: 45 },
        { name: 'test_health_check_endpoint', status: 'pass', duration: 28 },
      ],
      summary: { total: 3, passed: 3, failed: 0, skipped: 0 },
    },
    {
      kind: 'build_step',
      id: uid(),
      step: 'flake8 backend/app/',
      status: 'success',
      duration: 600,
      output: ['✓ Python linting checks passed cleanly.'],
    },
    {
      kind: 'summary',
      id: uid(),
      title: 'FastAPI Backend Core Created',
      description: 'Built FastAPI backend structure with Pydantic domain schemas and Pytest validation.',
      filesCreated: ['backend/main.py', 'backend/app/models.py'],
      commandsExecuted: ['git status', 'pytest backend/tests/test_users.py', 'flake8 backend/app/'],
      verified: ['FastAPI app initialization', 'Pytest test suite (3 passed)', 'Python PEP8 linting validation'],
    },
  ],
});
