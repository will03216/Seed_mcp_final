"""seed auth — credential management commands."""
from __future__ import annotations

import typer
from rich.prompt import Prompt

from seed import SeedClient
from seed.credentials import (
    clear_credentials,
    credentials_configured,
    write_credentials,
)
from seed.exceptions import SeedError

from ..console import console, err, info, ok, warn

app = typer.Typer(help="Manage Seed credentials.")


@app.command("login")
def login(
    profile: str = typer.Option("default", help="Credentials profile name."),
) -> None:
    """Interactively store provider credentials in ~/.seed/credentials.

    BytePlus is the default provider; fal.ai is optional. Enter at least one.
    """
    console.print("\n[bold]Seed — credential setup[/bold]")
    console.print("Credentials are stored in [cyan]~/.seed/credentials[/cyan] (chmod 600).")
    console.print("Enter at least one provider key (leave the other blank to skip).\n")

    console.print("[bold]BytePlus[/bold] (default) — [url]https://console.byteplus.com/voice/[/url]")
    byteplus_key = Prompt.ask(
        "  BYTEPLUS_SEED_API_KEY", password=True, default="", show_default=False
    )

    console.print("\n[bold]Seed LLM[/bold] (optional) — [url]https://console.byteplus.com/ark/[/url]")
    ark_key = Prompt.ask("  ARK_API_KEY", password=True, default="", show_default=False)

    console.print("\n[bold]fal.ai[/bold] (optional) — [url]https://fal.ai/dashboard/keys[/url]")
    fal_key = Prompt.ask("  FAL_KEY", password=True, default="", show_default=False)

    if not byteplus_key and not fal_key and not ark_key:
        err("At least one provider key is required. Aborting.")
        raise typer.Exit(1)

    write_credentials(
        fal_key.strip(),
        byteplus_seed_api_key=byteplus_key.strip(),
        ark_api_key=ark_key.strip(),
        profile=profile,
    )
    ok(f"Credentials saved to ~/.seed/credentials  [profile: {profile}]")

    info("Verifying configuration with seed ping…")
    try:
        result = SeedClient(profile=profile).ping()
        ok(f"Ready  (SDK v{result['version']}, provider: {result['provider']})")
    except SeedError as exc:
        warn(f"Saved, but ping failed: {exc}")


@app.command("check")
def check(
    profile: str = typer.Option("default", help="Credentials profile name."),
) -> None:
    """Check which credentials are currently configured."""
    status = credentials_configured(profile=profile)
    console.print(f"\n[bold]Credential status[/bold]  (profile: [cyan]{profile}[/cyan])\n")

    byteplus_legacy = status["byteplus_seed_app_id"] and status["byteplus_seed_access_key"]
    for label, present in [
        ("BYTEPLUS_SEED_API_KEY  (audio, default)     ", status["byteplus_seed_api_key"]),
        ("BYTEPLUS_SEED_APP_ID + ACCESS_KEY (legacy)  ", byteplus_legacy),
        ("ARK_API_KEY            (Seed LLM / text)    ", status["ark_api_key"]),
        ("FAL_KEY                (fal.ai provider)    ", status["fal_key"]),
    ]:
        mark = "[success]✔[/success]" if present else "[error]✖[/error]"
        state = "configured" if present else "missing"
        console.print(f"  {mark}  {label}  [dim]{state}[/dim]")

    if status["byteplus_seed_api_key"] or byteplus_legacy or status["fal_key"] or status["ark_api_key"]:
        console.print("\n  [success]At least one provider is configured — ready to generate.[/success]\n")
    else:
        console.print("\n  [error]No provider configured.[/error]")
        console.print("  Run [cyan]seed auth login[/cyan] to configure.\n")
        raise typer.Exit(1)


@app.command("logout")
def logout(
    profile: str = typer.Option("default", help="Credentials profile to remove."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Remove stored credentials for a profile."""
    if not yes:
        typer.confirm(f"Remove credentials for profile '{profile}'?", abort=True)
    existed = clear_credentials(profile=profile)
    if existed:
        ok(f"Credentials removed for profile '{profile}'.")
    else:
        warn("No credentials file found — nothing to remove.")
