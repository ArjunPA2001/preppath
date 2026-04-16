import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

load_dotenv()

import models
from database import engine, SessionLocal
import seed
from routers import candidate, session, assessment, questions, pipeline, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables
    models.Base.metadata.create_all(bind=engine)
    # Seed once (idempotent)
    db = SessionLocal()
    try:
        seed.run_seed(db)
    finally:
        db.close()
    yield


app = FastAPI(title="PrepPath", lifespan=lifespan)

# CORS — the Vite dev server runs on :5173 and calls the API directly
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (HTML pages)
app.mount("/static", StaticFiles(directory="static"), name="static")

# API routers
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(candidate.router, prefix="/candidates", tags=["candidates"])
app.include_router(session.router, prefix="/sessions", tags=["sessions"])
app.include_router(assessment.router, prefix="/assessments", tags=["assessments"])
app.include_router(questions.router, prefix="/questions", tags=["questions"])
app.include_router(pipeline.router, prefix="/pipelines", tags=["pipelines"])


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")
