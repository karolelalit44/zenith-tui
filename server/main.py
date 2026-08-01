"""CLI entry point — Zenith AI Coding Assistant Backend."""

from __future__ import annotations

import click


@click.group()
@click.version_option(package_name="zenith")
def cli():
    """Zenith AI Coding Assistant Backend"""


@cli.command()
@click.option("--host", default="localhost", help="Host to bind to")
@click.option("--port", default=8765, type=int, help="Port to listen on")
def serve(host: str, port: int):
    """Start the WebSocket server"""
    import uvicorn

    from server.api.server import create_app

    app = create_app()
    uvicorn.run(app, host=host, port=port, ws_ping_interval=None, ws_ping_timeout=None)


@cli.command()
def status():
    """Show current configuration and provider status"""
    from server.config.loader import load_config
    from server.providers.registry import ProviderRegistry

    config = load_config()
    registry = ProviderRegistry.from_config(config.providers, config.active_provider)

    click.echo(f"Active provider: {config.active_provider}")
    click.echo(f"Workspace:       {config.workspace_root}")
    click.echo(f"DB path:         {config.db_path}")
    click.echo(f"Providers:       {registry.list_providers()}")

    provider = registry.get(config.active_provider)
    if provider:
        click.echo(f"Model:           {provider.model}")
    else:
        click.echo("Model:           (none)")


@cli.command()
def tools():
    """List available tools"""
    from server.toolkit import create_default_registry

    registry = create_default_registry()
    schemas = registry.get_schemas()

    for s in schemas:
        risk = "safe"
        tool = registry.get(s["name"])
        if tool and hasattr(tool, "risk_level"):
            risk = tool.risk_level
        click.echo(f"  {s['name']:20s}  risk={risk:6s}  {s['description'][:60]}")

    click.echo(f"\nTotal: {len(schemas)} tools")


if __name__ == "__main__":
    cli()
