"""seed models — list available models."""
from __future__ import annotations

import typer

from seed import SeedClient
from seed.exceptions import SeedError

from ..console import console, err
from ..formatters import llm_models_table, models_table

app = typer.Typer(help="List available Seed models.")


@app.callback(invoke_without_command=True)
def models(
    ctx: typer.Context,
    profile: str = typer.Option("default", "--profile", help="Credentials profile."),
) -> None:
    """List all available Seed models (audio + LLM) and their capabilities."""
    if ctx.invoked_subcommand is not None:
        return

    client = SeedClient(profile=profile)
    try:
        audio = client.list_models()
        llm = client.list_llm_models()
    except SeedError as exc:
        err(str(exc))
        raise typer.Exit(1) from exc

    console.print()
    models_table(audio)
    console.print()
    llm_models_table(llm)
    console.print()
