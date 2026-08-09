"""Rich table/output formatters for CLI commands."""
from __future__ import annotations

from rich.table import Table

from .console import console


def voices_table(voices: list[str]) -> None:
    table = Table(title="Seed Audio voices", show_lines=False, header_style="bold cyan")
    table.add_column("#", style="dim", no_wrap=True)
    table.add_column("Voice id", style="blue")
    for i, v in enumerate(voices, 1):
        table.add_row(str(i), v)
    console.print(table)


def models_table(data: dict) -> None:
    table = Table(title="Available Models", show_lines=True, header_style="bold cyan")
    table.add_column("Model ID", style="blue", no_wrap=True)
    table.add_column("Label")
    table.add_column("Providers")
    table.add_column("Output formats")
    table.add_column("Sample rates")

    for m in data.get("models", []):
        table.add_row(
            m["model_id"],
            m.get("label", ""),
            ", ".join(m.get("providers", [])),
            ", ".join(m.get("output_formats", [])),
            ", ".join(str(s) for s in m.get("sample_rates", [])),
        )

    console.print(table)
    console.print(f"\n  Default:  [blue]{data.get('default_model', '')}[/blue]")
    console.print(f"  Provider: [blue]{data.get('provider', '')}[/blue]")


def llm_models_table(data: dict) -> None:
    table = Table(title="Seed LLM Models", show_lines=True, header_style="bold cyan")
    table.add_column("Model ID", style="blue", no_wrap=True)
    table.add_column("Label")
    table.add_column("Alias")
    table.add_column("Tools")
    table.add_column("MCP")
    table.add_column("Streaming")

    def _mark(v: object) -> str:
        return "✔" if v else "—"

    for m in data.get("models", []):
        table.add_row(
            m["model_id"],
            m.get("label", ""),
            m.get("alias", ""),
            _mark(m.get("supports_tools")),
            _mark(m.get("supports_mcp")),
            _mark(m.get("supports_streaming")),
        )

    console.print(table)
    console.print(f"\n  Default:  [blue]{data.get('default_model', '')}[/blue]")
    console.print(f"  Provider: [blue]{data.get('provider', '')}[/blue]")
