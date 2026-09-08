.PHONY: install dev test lint type-check demo docker-up docker-down migrate inspect clean

# Backend
install:
	cd backend && pip install -r requirements.txt

dev:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	cd backend && LLM_PROVIDER=mock pytest tests/ -v --tb=short

lint:
	cd backend && ruff check app/

type-check:
	cd backend && mypy app/ --ignore-missing-imports

# CLI
inspect:
	cd backend && python -m app.cli.inspect_pdfs --dir ../starter-datasets

demo:
	cd backend && python -m app.cli.demo

# Frontend
frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

# Docker
docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f api

# Database
migrate:
	cd backend && alembic upgrade head

# Cleanup
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -type f -name "*.pyc" -delete 2>/dev/null; \
	echo "Cleaned"
