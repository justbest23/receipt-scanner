# To use current build:
Go to basket.trog.co.za and register



# To run your own version of this app:
Followt the below instructions.

# Receipt Scanner — Backend v0.1

OCR + local LLM receipt parsing, fully dockerised.

## Requirements

- Docker + Docker Compose v2
- **NVIDIA Container Toolkit** (for GPU passthrough)
  - https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
  - After install: `sudo systemctl restart docker`

## Quick Start

### 1. Start the stack

```bash
docker compose up -d --build
```

First build pulls the PyTorch CUDA image (~4 GB) and downloads EasyOCR models.
Subsequent starts are fast.

### 2. Pull your LLM into Ollama

The default model is `llama3.1:8b`. Pull it once:

```bash
docker exec receipt-ollama ollama pull llama3.1:8b
```

Other good options for receipt extraction (all run fine on RTX 4080):
- `mistral:7b`        — fast, solid JSON
- `qwen2.5:7b`        — excellent at structured extraction
- `llama3.1:8b`       — best instruction following  ← default

To use a different model:

```bash
OLLAMA_MODEL=qwen2.5:7b docker compose up -d
```

Or set it permanently in a `.env` file:
```
OLLAMA_MODEL=qwen2.5:7b
```

### 3. Open the web UI

```
http://localhost:8000
```

Upload a receipt image and click **Run Pipeline**.

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health + Ollama status |
| POST | `/scan` | Upload image → run pipeline → save |
| GET | `/receipts` | List all receipts |
| GET | `/receipts/{id}` | Single receipt with items |
| DELETE | `/receipts/{id}` | Delete receipt |

API docs: `http://localhost:8000/docs`

## Architecture

```
browser
  └─ POST /scan (multipart image)
       └─ EasyOCR (GPU)        → raw text + per-line confidence
       └─ Ollama (local LLM)   → structured JSON
            ├─ store name + confidence
            ├─ date
            ├─ line items (name, qty, unit type, price, VAT flag)
            └─ totals
       └─ PostgreSQL           → persisted
  └─ GET /receipts             → history
```

## GPU Notes

Both `backend` and `ollama` containers request GPU access.
They share the RTX 4080 — EasyOCR uses it briefly during OCR, then Ollama uses it for inference.
They don't run simultaneously, so no contention in practice.

To verify GPU is visible inside containers:
```bash
docker exec receipt-backend nvidia-smi
docker exec receipt-ollama nvidia-smi
```

## Logs

```bash
docker compose logs -f backend    # FastAPI + pipeline logs
docker compose logs -f ollama     # LLM inference logs
```

## Stopping

```bash
docker compose down           # stop, keep data volumes
docker compose down -v        # stop + wipe all data
```
