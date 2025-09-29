# Contributing

Thanks for contributing to Fix Assistant! This guide shows how to set up your environment, match CI checks locally, and run tests.

## Supported Python versions
- We test on Python 3.12 and 3.13 in CI.

## Quick start
```bash
# From the repo root
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

# Run all quality checks (same as CI)
ruff check src/backend/app
black --check src/backend/app
mypy src/backend/app
pytest -v --cov=backend.app --cov-report=term-missing
```

## Development tips
- Editable install: with `-e`, changes under `src/` are picked up immediately.
- Tests are under `tests/` and include unit + integration.
- Type checking uses mypy; code is typed to pass under the strict config in `pyproject.toml`.
- Lint/format: ruff and black use line length 100.

## Running the backend locally
```bash
source .venv/bin/activate
# Default port from QC_PORT; we recommend 18001 if 18000 is taken
QC_PORT=18001 uvicorn backend.app.main:app --host 127.0.0.1 --port 18001
```

Endpoints:
- GET /health → {"status":"ok"}
- GET /assistant/config → config + server_port
- POST /assistant/inline → { completion: "..." }
- GET /assistant/sse → demo stream
- WS /assistant/ws → demo echo with schema validation

## Optional observability
- Set `QC_METRICS=1` (and install `prometheus-fastapi-instrumentator`) to expose `/metrics`.
- Set `QC_OTEL=1` (and install `opentelemetry-instrumentation-fastapi`) to enable tracing.

## Pull request checklist
- [ ] `ruff check src/backend/app`
- [ ] `black --check src/backend/app`
- [ ] `mypy src/backend/app`
- [ ] `pytest -v`

CI runs the same checks on push/PR via `.github/workflows/ci.yml`.
