# HR MCP — HR Handbook & Policy MCP for GIA

FastAPI service that answers HR policy questions and returns employee-specific details by integrating:

- GIA/OWUI for RAG over the Employee Handbook
- Microsoft Graph/Power Automate for employee metadata
- Vantagepoint for PTO balances

OpenAPI docs are available at `/docs` and `/redoc` when running locally.

## Features

- Ask HR policy questions with source/page citations: `POST /ask-file`
- Get leadership & employment summary (HRP, Director, MVP/EVP, CLL, tenure, etc.): `POST /get-my-leadership`
- Get your current vacation balance from Vantagepoint: `POST /get-my-vacation`
- One-call PTO answer (balance + handbook accrual explanation with citations): `POST /answer-my-pto`
- Robust model resolution against GIA `/api/models` (handles many payload shapes)
- Flexible handling of OWUI responses (JSON, SSE, NDJSON, or text)

## Requirements

- Python 3.10+
- Access to your GIA/OWUI instance and the Employee Handbook indexed there
- Access to Power Automate (Flow) endpoint used by your tenant
- Access to Vantagepoint and credentials to obtain an API token

## Project Structure

- `main.py` — FastAPI app and endpoints
- `auth/` — Vantagepoint auth helper (`get_vantagepoint_token`)
- `utils/` — Config helpers
- `test_scripts/` — Ad-hoc test scripts for local verification
- `requirements.txt` / `pyproject.toml` — dependencies
- `Dockerfile`, `compose.yaml` — containerization

## Configuration (.env)

Environment variables are loaded via `python-dotenv`.

Minimum required:

- `OWUI_JWT` — Bootstrap JWT used to exchange for a service token
- `GIA_URL` — Base URL of your GIA/OWUI gateway (e.g., https://gia.example.com)
- `HARDCODED_FILE_ID` — File id of the Employee Handbook in GIA
- `PA_URL` — Power Automate flow HTTPS endpoint (for employee metadata)
- `VP_BASE_URL` — Vantagepoint API base URL
- `VP_SP_GETVACATION` — Name of the Vantagepoint stored procedure used for PTO

Optional:

- `OPENAI_API_KEY` — If you use any post-processing with OpenAI
- `OPENAI_MODEL` — Defaults to `gpt-4o-mini`
- `DEBUG` — Set to `1`/`true` for verbose logs
- `GRAPH_TOKEN_URL`, `GRAPH_CLIENT_ID`, `GRAPH_SECRET` — If your Flow requires Entra ID token acquisition

Example `.env`:

```
GIA_URL=https://gia.example.com
OWUI_JWT=eyJhbGciOi...
HARDCODED_FILE_ID=handbook-file-id
PA_URL=https://prod-00.westus.logic.azure.com:443/workflows/.../triggers/manual/paths/invoke
VP_BASE_URL=https://vantagepoint.example.com
VP_SP_GETVACATION=HR_GetVacationBalances
DEBUG=1
```

## Install & Run (local)

1. Install dependencies

```bash
pip install -r requirements.txt
```

2. Start the API with Uvicorn (port 5001)

```bash
uvicorn "main:app" --host 0.0.0.0 --port 5001 --reload
```

Visit http://localhost:5001/docs

## Docker

Build and run the container:

```bash
docker build -t hr-mcp .
docker run --rm -p 5001:5001 --env-file .env hr-mcp
```

With Docker Compose (service name: `vantagepoint-server`):

```bash
docker compose up --build
```

The app will be available at http://localhost:5001

## API Summary

### POST /ask-file

Ask HR policy questions against the Employee Handbook in GIA.

- Body: `{ "question": "...", "model": "gpt-5", "stream": true }`
- Returns: `normalized_text`, `sources[]`, and `instructions` prompting citation of page numbers.

### POST /get-my-leadership

Returns leadership and employment summary for the authenticated user (via OWUI auth).

- Returns: `leadership{...}`, `summary{...}` (employee id, display name, email, CLL, tenure, etc.).

### POST /get-my-vacation

Returns current and starting PTO balances from Vantagepoint for the authenticated user.

- Returns: `employee_id`, `starting_balance`, `current_balance`, plus `instructions` to present in hours and days (8h/day).

### POST /answer-my-pto

Combines your PTO balance with a handbook-backed accrual explanation and citations.

- Returns: `vacation{...}`, `accrual_explanation`, `citations[]`, `used_tools`.

## Testing

Pytest is configured in `requirements.txt`.

```bash
pytest -q
```

## Troubleshooting

- 502 from GIA endpoints: verify `OWUI_JWT`, network access to `GIA_URL`, and that the Handbook file id exists and is processed.
- Empty PTO results: confirm Vantagepoint token retrieval and `VP_SP_GETVACATION` name.
- Power Automate errors: check `PA_URL` and, if needed, `GRAPH_*` credentials.

## License

This repo is made available for demonstration purposes only. No license is granted for reuse.
