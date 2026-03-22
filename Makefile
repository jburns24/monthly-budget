.PHONY: help install lint test up down clean

help:
	@echo "Monthly Budget - Available commands:"
	@echo ""
	@echo "  make install         Install pre-commit hooks, backend deps, and frontend deps"
	@echo "  make lint            Run all code quality checks (pre-commit)"
	@echo "  make test            Run backend pytest and frontend vitest"
	@echo "  make up              Start all services (docker compose up -d)"
	@echo "  make down            Stop all services (docker compose down)"
	@echo "  make clean           Clean up generated files and caches"

install:
	@echo "Installing pre-commit hooks..."
	pre-commit install
	@echo "Installing backend dependencies..."
	cd backend && uv sync --all-groups
	@echo "Installing frontend dependencies..."
	cd frontend && npm install
	@echo "Installation complete!"

lint:
	@echo "Running all code quality checks..."
	pre-commit run --all-files

test:
	@echo "Running backend tests..."
	cd backend && uv run pytest
	@echo "Running frontend tests..."
	cd frontend && npm run test:run

up:
	@echo "Starting all services..."
	docker compose up -d

down:
	@echo "Stopping all services..."
	docker compose down

clean:
	@echo "Cleaning up generated files..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .venv -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name dist -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete!"
