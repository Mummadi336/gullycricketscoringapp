from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.matches import router as matches_router
from app.api.scoring import router as scoring_router
from app.api.statistics import router as statistics_router
from app.api.teams import router as teams_router
from app.database import engine, initialize_database
from app.security import require_api_auth, validate_auth_configuration


APP_DIRECTORY = Path(__file__).resolve().parent
STATIC_DIRECTORY = APP_DIRECTORY / "static"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    validate_auth_configuration()
    initialize_database()

    yield

    engine.dispose()


app = FastAPI(
    title="GullyScore",
    description="Gully cricket scoring application",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIRECTORY),
    name="static",
)
app.include_router(teams_router, prefix="/api")
app.include_router(matches_router, prefix="/api")
app.include_router(scoring_router, prefix="/api")
app.include_router(statistics_router, prefix="/api")


@app.get("/", include_in_schema=False, dependencies=[Depends(require_api_auth)])
def home() -> FileResponse:
    return FileResponse(STATIC_DIRECTORY / "index.html")


@app.get("/api/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
