"""FastAPI application for the exo dashboard.

Lightweight: server-rendered Jinja2 templates with HTMX for the bits of
interactivity (view toggle, strategy switcher). Static assets for CSS.
No build step.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .data import build_view_model


def create_app(default_fleet_path: str | Path = "fleet.yaml") -> FastAPI:
    base_dir = Path(__file__).resolve().parent
    templates = Jinja2Templates(directory=str(base_dir / "templates"))
    app = FastAPI(title="exo dashboard", version="0.6.0")
    app.mount("/static",
              StaticFiles(directory=str(base_dir / "static")),
              name="static")

    default_path = Path(default_fleet_path)

    def _vm(fleet_path: Optional[str], strategy: str):
        p = Path(fleet_path) if fleet_path else default_path
        return build_view_model(p, strategy=strategy)

    @app.get("/", response_class=HTMLResponse)
    def topology(request: Request,
                 fleet: Optional[str] = None,
                 strategy: str = "specialized"):
        vm = _vm(fleet, strategy)
        return templates.TemplateResponse(
            "topology.html",
            {"request": request, "vm": vm, "view": "topology"},
        )

    @app.get("/pulse", response_class=HTMLResponse)
    def pulse(request: Request,
              fleet: Optional[str] = None,
              strategy: str = "specialized"):
        vm = _vm(fleet, strategy)
        return templates.TemplateResponse(
            "pulse.html",
            {"request": request, "vm": vm, "view": "pulse"},
        )

    @app.get("/api/fleet")
    def api_fleet(fleet: Optional[str] = None,
                  strategy: str = "specialized"):
        vm = _vm(fleet, strategy)
        # Return a JSON-friendly dict
        return JSONResponse({
            "name": vm.name,
            "description": vm.description,
            "strategy": vm.strategy,
            "hosts": [{
                "name": h.name, "cpu_threads": h.cpu_threads, "ram_mb": h.ram_mb,
                "has_gpu": h.has_gpu, "gpu_model": h.gpu_model,
                "role_hint": h.role_hint,
                "workloads": h.workloads,
                "ram_used_mb": h.ram_used_mb, "ram_used_pct": h.ram_used_pct,
                "status": h.status,
                "proposed_workloads": h.proposed_workloads,
                "proposed_ram_used_pct": h.proposed_ram_used_pct,
            } for h in vm.hosts],
            "moves": vm.moves,
            "waves": vm.waves,
            "violations": vm.violations,
            "metrics": vm.metrics,
        })

    @app.get("/api/sessions")
    def api_sessions(limit: int = 20):
        try:
            from exo_runtime.memory import MemoryStore
            with MemoryStore() as s:
                return JSONResponse({"sessions": s.all_sessions(limit=limit)})
        except Exception as e:
            return JSONResponse({"sessions": [], "error": str(e)})

    @app.get("/api/health")
    def api_health():
        return {"ok": True, "default_fleet": str(default_path),
                "fleet_exists": default_path.exists()}

    return app
