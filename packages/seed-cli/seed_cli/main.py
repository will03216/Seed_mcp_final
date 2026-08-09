"""Seed CLI — entry point.

Usage:
    seed auth login
    seed generate --prompt "..." --voice sophie_en_zh --watch
    seed status <request_id>
    seed watch <request_id>
    seed voices
    seed models
    seed skill install
    seed skill check
"""
from __future__ import annotations

import typer

from .commands import auth, chat, generate, models, skill, tasks, voices

app = typer.Typer(
    name="seed",
    help="BytePlus Seed CLI — audio generation + LLM text generation.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

# Top-level command groups
app.add_typer(auth.app,     name="auth",     help="Manage Seed credentials.")
app.add_typer(generate.app, name="generate", help="Submit audio generation jobs.")
app.add_typer(chat.app,     name="chat",     help="Generate text with a Seed LLM.")
app.add_typer(tasks.app,    name="tasks",    help="Manage generation tasks.")
app.add_typer(voices.app,   name="voices",   help="List Seed Audio preset voices.")
app.add_typer(models.app,   name="models",   help="List available Seed models.")
app.add_typer(skill.app,    name="skill",    help="Install/manage the Claude Code skill.")

# Convenience shortcuts at the top level
app.command("status", help="Check the status of a task.")(tasks.status)
app.command("watch",  help="Stream live progress for a task.")(tasks.watch)


@app.command("ping")
def ping(
    profile: str = typer.Option("default", "--profile", help="Credentials profile."),
) -> None:
    """Verify provider connectivity and credential configuration."""
    from seed import SeedClient
    from seed.exceptions import SeedError

    from .console import console, err, info, ok

    client = SeedClient(profile=profile)
    try:
        result = client.ping()
    except SeedError as exc:
        err(str(exc))
        raise typer.Exit(1) from exc

    console.print()
    ok(f"Ready  (SDK v{result['version']}, provider: {result['provider']})")
    creds = result.get("credentials", {})
    for key, label in [
        ("fal_key", "FAL_KEY                "),
        ("byteplus_seed_api_key", "BYTEPLUS_SEED_API_KEY  "),
        ("ark_api_key", "ARK_API_KEY (Seed LLM) "),
    ]:
        mark = "[success]✔[/success]" if creds.get(key) else "[error]✖[/error]"
        info(f"{mark}  {label}  {'configured' if creds.get(key) else 'missing'}")
    console.print()


if __name__ == "__main__":
    app()
