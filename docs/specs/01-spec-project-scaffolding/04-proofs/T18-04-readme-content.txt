Type: file
Description: Verify README.md contains quickstart instructions and prerequisites
Expected: README.md exists with prerequisites (Docker, Python 3.12+, Node 20+, uv, pre-commit) and quickstart steps
Timestamp: 2026-03-22T16:51:52Z

Command: head -50 /Users/jburns/git/monthly-budget/README.md

Output:
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

Verification:
✓ Prerequisites section includes: Docker, Python 3.12+, Node 20+, uv, pre-commit
✓ Quick Start section with 5 steps (Clone, Copy env, Install, Start, Verify)
✓ Common Commands section with make lint, make test, make down, make clean
✓ Project Structure section describing layout
✓ Development Workflow section
✓ Troubleshooting section with helpful tips
✓ API Documentation section pointing to Swagger UI and ReDoc

Status: PASS

Details: README.md created with comprehensive quickstart instructions, prerequisites, and troubleshooting guide
