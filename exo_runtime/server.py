"""Minimal API server for the exo-runner container. v0.1 is a stub.

Real value-add (web UI, real-time transcript streaming, etc.) is roadmapped.
For v0.1, the CLI is the primary interface.
"""
from __future__ import annotations

import os
from fastapi import FastAPI

app = FastAPI(title="exo runner", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"service": "exo-runner", "status": "ok", "version": "0.1.0"}


@app.get("/")
def root() -> dict:
    return {
        "message": "exo runner is up. Use the `exo` CLI for v0.1; web UI in v0.2.",
        "docs": "https://github.com/MGBuilds9/exo",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "5050")))
