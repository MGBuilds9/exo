"""exo plan — fleet rebalancing.

Inputs a fleet description (hosts + workloads + constraints), runs constrained
bin-packing, outputs a rebalanced placement + migration plan as markdown.

Different from `exo solve` (which diagnoses a single component) — plan operates
on the whole fleet at once. Different from `exo recommend` (which picks
external repos) — plan operates on workloads you already own.
"""
from .fleet import Fleet, Host, Workload, ConstraintViolation, load_fleet
from .balancer import (
    PlacementStrategy, Placement, balance_fleet, evaluate_placement,
)
from .migration import MigrationPlan, MigrationWave, build_migration_plan

__all__ = [
    "Fleet", "Host", "Workload", "ConstraintViolation", "load_fleet",
    "PlacementStrategy", "Placement", "balance_fleet", "evaluate_placement",
    "MigrationPlan", "MigrationWave", "build_migration_plan",
]
