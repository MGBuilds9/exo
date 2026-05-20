"""exo dashboard — visual surface for the fleet.

FastAPI + Jinja2 + HTMX. Reads from fleet.yaml + ~/.exo/sessions.db.
Two views per DESIGN.md: Topology (default daily-driver) + Pulse (glance).

Routes:
  GET  /                     — Topology view
  GET  /pulse                — Pulse view
  GET  /api/fleet            — fleet.yaml as JSON
  GET  /api/plan             — run exo plan, return JSON
  GET  /api/sessions         — recent execute sessions
  GET  /api/discover-summary — last discover unmanaged report
"""
from .app import create_app
from .data import FleetViewModel, build_view_model

__all__ = ["create_app", "FleetViewModel", "build_view_model"]
