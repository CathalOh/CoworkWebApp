.PHONY: up down dev test test-pg lint spike seed
up:        ; docker compose up --build
down:      ; docker compose down -v
dev:       ; ./scripts/dev.sh
lint:      ; cd backend && . .venv/bin/activate && ruff check app tests && cd ../frontend && npm run typecheck
test:      ; cd backend && . .venv/bin/activate && pytest -q && pytest -q ../tests/mock_iliad
test-pg:   ; cd backend && . .venv/bin/activate && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app pytest -q
e2e:       ; cd tests/e2e && npx playwright test
spike:     ; backend/.venv/bin/python scripts/iliad_spike.py
seed:      ; cd backend && . .venv/bin/activate && python -m app.seed
