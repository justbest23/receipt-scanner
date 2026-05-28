# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack

- **Backend**: FastAPI (Python 3.11) + SQLAlchemy + PostgreSQL 16
- **OCR/LLM**: Ollama (local, GPU-accelerated) with a multimodal vision model (default: `llama3.2-vision:11b`)
- **Infrastructure**: Fully Dockerised — three services: `backend`, `db`, `ollama`

## Running the stack

```bash
docker compose up -d --build          # Start (first run pulls ~4 GB PyTorch image)
docker compose logs -f backend        # Stream FastAPI + pipeline logs
docker compose down                   # Stop, keep volumes
docker compose down -v                # Stop + wipe all data
```

The backend hot-reloads from `./backend` (mounted into the container at `/app`), so Python edits take effect immediately without rebuilding.

To switch Ollama models:
```bash
OLLAMA_MODEL=qwen2.5:7b docker compose up -d
# or set permanently in .env: OLLAMA_MODEL=qwen2.5:7b
docker exec receipt-ollama ollama pull llama3.2-vision:11b   # pull the default model
```

Verify GPU visibility:
```bash
docker exec receipt-backend nvidia-smi
docker exec receipt-ollama nvidia-smi
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | API, DB, and Ollama status |
| POST | `/scan` | Upload image → run pipeline → return extracted data (no DB write) |
| POST | `/receipts/confirm` | Save user-reviewed pipeline result to DB |
| GET | `/receipts` | Paginated receipt list |
| GET | `/receipts/{id}` | Single receipt with line items |
| DELETE | `/receipts/{id}` | Delete receipt |
| GET | `/vendors` | List known vendor names |

Interactive docs: `http://localhost:8000/docs`

## Architecture

The pipeline intentionally separates extraction from persistence:

1. **`POST /scan`** — saves the uploaded image to disk, runs `pipeline.run_pipeline()`, and returns the raw extraction result. Nothing is written to the DB yet.
2. **`POST /receipts/confirm`** — the user reviews the extracted data in the frontend, then submits it here to persist.

### Two-stage LLM pipeline (`pipeline.py`)

- **Stage 1 — Vendor detection**: A fast Ollama call (`num_predict: 20`, `temperature: 0`) asks the vision model for the store name only.
- **Stage 2 — Full extraction**: `vendor.py` fuzzy-matches the detected name against `backend/vendors/*.json` profiles, builds a vendor-specific prompt section, injects it into `_BASE_PROMPT`, then calls Ollama again with `format: "json"` and `num_predict: 3000`.

The base extraction prompt (`pipeline._BASE_PROMPT`) defines the full JSON schema the LLM must return, South African VAT zero-rating rules, and general parsing rules. Vendor profiles override or supplement these.

### Vendor profiles (`backend/vendors/*.json`)

Each JSON file maps a vendor to its receipt parsing quirks:
- `aliases` — fuzzy-matched strings for vendor detection
- `vat_indicator` — how VAT is marked (e.g. Checkers uses `A` suffix on zero-rated prices)
- `quantity_rules`, `weight_rules`, `product_name_rules`, `discount_rules` — vendor-specific parsing instructions injected verbatim into the LLM prompt
- `store_name_rules.always_output` — canonical store name to emit regardless of what appears on the receipt
- `item_count_rules`, `prompt_notes` — additional LLM guidance

`unknown.json` is the fallback when no vendor is matched. Adding a new vendor means adding a JSON file here — no Python changes required.

### Database (`database.py`, `models.py`)

SQLAlchemy models are created at startup via `Base.metadata.create_all()`. Schema evolution is handled by `_migrate()` — a list of `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements that run idempotently on every startup. There is no Alembic migration history; new columns are added to `_migrate()` directly.

Two tables:
- `receipts` — header (store, date, vendor, totals, VAT, currency, `tax_groups` JSONB)
- `receipt_items` — line items linked by FK, including `receipt_name` (raw OCR text) and `name` (decoded display name)

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://receipt:receipt@db:5432/receipts` | Postgres connection string |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama service URL |
| `OLLAMA_MODEL` | `llama3.2-vision:11b` | Vision model for both pipeline stages |
| `UPLOAD_DIR` | `/app/uploads` | Where uploaded receipt images are stored |
