"""exo doctor — print hardware + services + accounts report and exit."""
from __future__ import annotations

import json as _json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from exo_runtime.doctor import run_doctor, recommend_from_doctor

console = Console()


def run(*, extra_hosts: list[str] | None = None, as_json: bool = False) -> None:
    report = run_doctor(extra_hosts=extra_hosts)
    if as_json:
        print(_json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return
    body = "\n".join(report.summary_lines)
    console.print(Panel.fit(Text(body), title="[bold]exo doctor[/bold]", border_style="cyan"))

    recs = recommend_from_doctor(report)
    rec_lines = []
    rec_lines.append(f"primary LLM:    {recs['primary_llm'] or 'NONE — configure at least one LLM endpoint'}")
    if recs["fallback_llm"]:
        rec_lines.append(f"fallback LLM:   {recs['fallback_llm']}")
    rec_lines.append(f"embedding:      {recs['embedding'] or 'none — vector tier disabled'}")
    rec_lines.append(f"vector store:   {recs['vector_store']}")
    rec_lines.append(f"graph store:    {recs['graph_store']}")
    rec_lines.append(f"sql store:      {recs['sql_store']}")
    rec_lines.append(f"hosting:        {recs['hosting_target']}")
    rec_lines.append("")
    rec_lines.append("notes:")
    for n in recs["notes"]:
        rec_lines.append(f"  - {n}")
    console.print(Panel.fit(Text("\n".join(rec_lines)),
                            title="[bold]Recommendations based on what you actually have[/bold]",
                            border_style="green"))
