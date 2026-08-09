"""seed chat — generate text with a Seed LLM (Ark Responses API)."""
from __future__ import annotations

import typer

from seed import SeedClient
from seed.exceptions import SeedError

from ..console import console, err, info

app = typer.Typer(help="Generate text with a Seed LLM.")


@app.callback(invoke_without_command=True)
def chat(
    ctx: typer.Context,
    prompt: str = typer.Option(..., "--prompt", "-p", help="The user message / task for the model."),
    model: str = typer.Option("", "--model", "-m", help="Model id or alias (pro | turbo | full id). Default: seed-2-0-pro-260328."),
    system: str = typer.Option("", "--system", "-s", help="Optional system instruction."),
    mcp_url: list[str] | None = typer.Option(None, "--mcp-url", help="Remote MCP server URL for the model to use. Repeatable."),
    mcp_label: list[str] | None = typer.Option(None, "--mcp-label", help="Label for the matching --mcp-url (same order). Optional."),
    temperature: float | None = typer.Option(None, "--temperature", "-t", help="Sampling temperature (0.0–2.0)."),
    max_output_tokens: int | None = typer.Option(None, "--max-tokens", help="Cap on generated tokens."),
    stream: bool = typer.Option(True, "--stream/--no-stream", help="Stream tokens live (default) or wait for the full result."),
    profile: str = typer.Option("default", "--profile", help="Credentials profile."),
) -> None:
    """Generate text with a Seed LLM.

    Attach remote MCP servers so the model can call their tools, e.g.:

        seed chat -p "check the repo structure expressjs/express" \\
          --mcp-url https://mcp.deepwiki.com/mcp --mcp-label deepwiki
    """
    if ctx.invoked_subcommand is not None:
        return

    mcp_servers = _build_mcp_servers(mcp_url, mcp_label)
    client = SeedClient(profile=profile)
    console.print()

    try:
        if stream:
            _stream(client, prompt, model, system, mcp_servers, temperature, max_output_tokens)
        else:
            _oneshot(client, prompt, model, system, mcp_servers, temperature, max_output_tokens)
    except SeedError as exc:
        err(str(exc))
        raise typer.Exit(1) from exc


def _build_mcp_servers(
    urls: list[str] | None, labels: list[str] | None
) -> list[dict] | None:
    if not urls:
        return None
    labels = labels or []
    servers = []
    for i, url in enumerate(urls):
        servers.append(
            {
                "server_label": labels[i] if i < len(labels) else f"mcp{i + 1}",
                "server_url": url,
                "require_approval": "never",
            }
        )
    return servers


def _stream(client, prompt, model, system, mcp_servers, temperature, max_output_tokens) -> None:
    got_output = False
    for delta in client.stream_text(
        prompt,
        model=model or None,
        system=system or None,
        mcp_servers=mcp_servers,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    ):
        console.print(delta, end="", markup=False, highlight=False)
        got_output = True
    console.print("\n")
    if not got_output:
        info("(no text output — the model may have only made tool calls)")


def _oneshot(client, prompt, model, system, mcp_servers, temperature, max_output_tokens) -> None:
    result = client.generate_text(
        prompt,
        model=model or None,
        system=system or None,
        mcp_servers=mcp_servers,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    console.print(result.text or "(no text output)", markup=False, highlight=False)
    console.print()
    if result.tool_calls:
        info(f"Tool calls: {len(result.tool_calls)}")
    if result.usage:
        info(f"Usage: {result.usage}")
