# Monthly Budget

A full-stack budget management application with FastAPI backend and React frontend.

## Prerequisites

- **Docker** and Docker Compose
- **Python** 3.12 or later
- **Node.js** 20 or later
- **uv** (Python package manager) - [install uv](https://docs.astral.sh/uv/getting-started/installation/)
- **pre-commit** - `pip install pre-commit` or `brew install pre-commit`
- **Tilt** (container orchestration) - `brew install tilt-dev/tap/tilt`
- **Task** (task runner) - `brew install go-task/tap/task`

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
task install
```

This will (in parallel):
- Install backend dependencies via uv
- Install frontend dependencies via npm
- Install pre-commit hooks for git

### 4. Start Services

```bash
task dev
```

This starts Tilt, which orchestrates all services with live-reload:
- **PostgreSQL** (port 5432)
- **Redis** (port 6379)
- **Backend API** (port 8000) - http://localhost:8000
- **Frontend** (port 5173) - http://localhost:5173
- **Tilt Dashboard** - http://localhost:10350

Alternatively, start without Tilt: `task up`

### 5. Verify Health

Check that the backend is running:

```bash
curl http://localhost:8000/api/v1/health
```

Open http://localhost:5173 in your browser to view the frontend.

## Common Commands

### Run Quality Checks

```bash
task lint
```

Runs all code quality checks:
- ruff (Python linting and formatting)
- mypy (type checking)
- eslint (JavaScript/TypeScript linting)
- prettier (code formatting)
- detect-secrets (security baseline)

### Run Tests

```bash
task test
```

Runs backend + frontend tests in parallel.

### Backend Commands

```bash
task be:test                         # Run backend tests
task be:lint                         # Ruff check + format check
task be:format                       # Auto-format
task be:db:migrate                   # Run database migrations
task be:db:revision MSG="add users"  # Generate a new migration
task be:db:downgrade                 # Downgrade one revision
```

### Frontend Commands

```bash
task fe:test              # Run frontend tests
task fe:lint              # ESLint
task fe:format            # Prettier
task fe:typecheck         # TypeScript type checking
task fe:build             # Build for production
```

### Stop Services

```bash
task dev:down    # Stop Tilt
task down        # Stop docker compose (if started with task up)
```

### Clean Generated Files

```bash
task clean
```

Removes:
- Python cache directories (__pycache__, .pytest_cache, .ruff_cache)
- Frontend node_modules and dist

### List All Available Tasks

```bash
task --list
```

## Project Structure

```
monthly-budget/
├── backend/                  # FastAPI application
│   ├── app/                  # Application source code
│   ├── alembic/              # Database migrations
│   ├── tests/                # Backend tests
│   ├── Dockerfile            # Backend container image
│   ├── Taskfile.yml          # Backend task definitions
│   └── pyproject.toml        # Python dependencies and config
├── frontend/                 # React application
│   ├── src/                  # Source code
│   ├── public/               # Static assets
│   ├── Dockerfile            # Frontend container image
│   ├── Taskfile.yml          # Frontend task definitions
│   └── package.json          # JavaScript dependencies
├── docker-compose.yml        # Service definitions
├── Tiltfile                  # Container orchestration + live-reload
└── Taskfile.yml              # Root task orchestrator
```

## Development Workflow

1. **Start the dev environment**: `task dev`
2. **Make code changes** in backend/ or frontend/ — Tilt live-reloads automatically
3. **Pre-commit hooks run automatically** before each commit
4. **Run tests locally**: `task test`
5. **Run quality checks**: `task lint`
6. **Commit your changes** when tests and lint pass

Use the Tilt dashboard at http://localhost:10350 to monitor services, view logs, and run actions (migrate, test, lint) via UI buttons.

For more details on code quality standards, see `.pre-commit-config.yaml`.

## Troubleshooting

### Port Already in Use

If ports 5432, 6379, 8000, or 5173 are already in use:

```bash
# Find what's using a port (example: port 8000)
lsof -i :8000

# Stop services and try again
task dev:down
task dev
```

### Pre-commit Hook Failures

If a pre-commit hook fails:

```bash
# Fix the issues (lint/format)
task be:format
task fe:format
```

Then commit again.

### Backend Connection Issues

Ensure services are running:

```bash
docker compose ps
```

Check logs:

```bash
docker compose logs api
docker compose logs db
docker compose logs redis
```

## API Documentation

Once the backend is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## License

MIT
