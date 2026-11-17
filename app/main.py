"""App factory: lifespan, middleware, error envelope, auto-registered routers and the SPA fallback.
Routes live in ``app/api/*``."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api import errors, register_routers
from app.db.session import create_all, get_session
from app.logging_setup import RequestContextMiddleware, configure_logging
from app.seed import run as seed_run
from app.settings import validate_required

validate_required()  # fail fast, naming any missing variable (never its value)

FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "dist"
SEED_STORAGE = Path("storage")  # where the seeded demo PDFs are written


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Development convenience: create the tables and seed an empty database.
    Production databases are managed with Alembic (``alembic upgrade head``) and ``python -m app.seed.run``."""
    create_all()
    with get_session() as session:
        seed_run.seed_if_empty(session, SEED_STORAGE)
    yield


app = FastAPI(title="Claim Fraud Detection Agents", lifespan=lifespan)

configure_logging()
app.add_middleware(RequestContextMiddleware)
errors.install(app)
register_routers(app)  # must precede the SPA catch-all below


# ---------------------------------------------------------------- frontend (built React app)

if (FRONTEND / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404, "Not found")
    candidate = (FRONTEND / full_path).resolve()
    if full_path and candidate.is_file() and FRONTEND.resolve() in candidate.parents:
        return FileResponse(candidate)
    index = FRONTEND / "index.html"
    if not index.exists():
        return Response("Frontend not built. Run: cd frontend; npm install; npm run build", media_type="text/plain")
    return FileResponse(index)
