# Monthly Budget

A full-stack budget management application with FastAPI backend and React frontend.

## Prerequisites

- **Docker** and Docker Compose
- **Python** 3.12 or later
- **Node.js** 20 or later
- **uv** (Python package manager) - [install uv](https://docs.astral.sh/uv/getting-started/installation/)
- **pre-commit** - `pip install pre-commit` or `brew install pre-commit`

## Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd monthly-budget
```

### 2. Copy Environment Files

```bash
# Backend environment configuration
cp backend/.env.example backend/.env

# Frontend environment configuration
cp frontend/.env.example frontend/.env
```

Edit the `.env` files with your actual configuration values:
- **backend/.env**: Database URL, Redis URL, API keys for Google OAuth and Anthropic
- **frontend/.env**: API base URL (default: http://localhost:8000)

### 3. Install Dependencies and Pre-commit Hooks

```bash
make install
```

This will:
- Install pre-commit hooks for git
- Install backend dependencies via uv
- Install frontend dependencies via npm

### 4. Start Services

```bash
make up
```

This starts:
- **PostgreSQL** (port 5432)
- **Redis** (port 6379)
- **Backend API** (port 8000) - http://localhost:8000
- **Frontend** (port 5173) - http://localhost:5173

### 5. Verify Health

Check that the backend is running:

```bash
curl http://localhost:8000/api/v1/health
```

Open http://localhost:5173 in your browser to view the frontend.

## Common Commands

### Run Quality Checks

```bash
make lint
```

Runs all code quality checks:
- ruff (Python linting and formatting)
- mypy (type checking)
- eslint (JavaScript/TypeScript linting)
- prettier (code formatting)
- detect-secrets (security baseline)

### Run Tests

```bash
make test
```

Runs:
- Backend tests: `pytest`
- Frontend tests: `vitest`

### Stop Services

```bash
make down
```

### Clean Generated Files

```bash
make clean
```

Removes:
- Python cache directories (__pycache__, .pytest_cache, .ruff_cache)
- Frontend node_modules and dist
- Virtual environments

## Project Structure

```
monthly-budget/
├── backend/                  # FastAPI application
│   ├── app/                  # Application source code
│   ├── alembic/              # Database migrations
│   ├── tests/                # Backend tests
│   ├── Dockerfile            # Backend container image
│   └── pyproject.toml        # Python dependencies and config
├── frontend/                 # React application
│   ├── src/                  # Source code
│   ├── public/               # Static assets
│   ├── Dockerfile            # Frontend container image
│   └── package.json          # JavaScript dependencies
├── docker-compose.yml        # Service orchestration
└── Makefile                  # Developer convenience commands
```

## Development Workflow

1. **Make code changes** in backend/ or frontend/
2. **Pre-commit hooks run automatically** before each commit
3. **Run tests locally**: `make test`
4. **Run quality checks**: `make lint`
5. **Commit your changes** when tests and lint pass

For more details on code quality standards, see `.pre-commit-config.yaml`.

## Troubleshooting

### Port Already in Use

If ports 5432, 6379, 8000, or 5173 are already in use:

```bash
# Find what's using a port (example: port 8000)
lsof -i :8000

# Stop services and try again
make down
make up
```

### Pre-commit Hook Failures

If a pre-commit hook fails:

```bash
# Fix the issues (lint/format)
cd backend && uv run ruff format .
cd frontend && npm run format
```

Then commit again.

### Backend Connection Issues

Ensure services are running:

```bash
docker compose ps
```

Check logs:

```bash
docker compose logs backend
docker compose logs postgres
docker compose logs redis
```

## API Documentation

Once the backend is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## License

MIT
