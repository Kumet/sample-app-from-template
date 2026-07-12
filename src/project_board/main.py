"""FastAPI entry point for Local Project Board."""

from fastapi import FastAPI

app = FastAPI(title="Local Project Board")


@app.get("/health")
def health() -> dict[str, str]:
    """Return the process health without consulting external resources."""
    return {"status": "ok"}
