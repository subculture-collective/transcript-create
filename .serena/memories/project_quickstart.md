# Transcript Create – Serena Quickstart

- Path: /home/onnwee/Documents/Code/onnwee/transcript-create
- Repo: onnwee/transcript-create (branch: main)
- Stack: FastAPI, SQLAlchemy (psycopg3), PostgreSQL, Alembic; Worker with Whisper (CT2/PyTorch), optional pyannote; Redis cache (optional); Docker Compose for local stack.

## How to run locally

- API: `uvicorn app.main:app --reload --port 8000`
- Worker: `python -m worker.loop`
- Docker: `docker compose up -d`
- DB (dev): `postgresql+psycopg://postgres:postgres@localhost:5435/transcripts`

## Serena

- Start MCP server (HTTP): Run VS Code task "Serena: Start MCP server (HTTP)" or:
  `uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project "/home/onnwee/Documents/Code/onnwee/transcript-create" --transport streamable-http --port 9121`
- Dashboard: <http://localhost:24282/dashboard/index.html>
- Index project: `uvx --from git+https://github.com/oraios/serena serena project index`

Notes: Native exports are public; YouTube exports require auth. Integration tests expect 404 when video/transcript missing; see `app/routes/exports.py` behavior.
