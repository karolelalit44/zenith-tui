from __future__ import annotations

import click

from server.config.constants import DEFAULT_HOST, DEFAULT_PORT, HOST_ENV_VAR, PORT_ENV_VAR


@click.group()
@click.version_option(package_name="zenith")
def cli():
    pass


@cli.command()
@click.option("--host", default=None, help="Host to bind to")
@click.option("--port", default=None, type=int, help="Port to listen on")
def serve(host: str | None, port: int | None):
    import os

    import uvicorn

    from server.api.server import create_app

    app = create_app()
    uvicorn.run(
        app,
        host=host or os.environ.get(HOST_ENV_VAR, DEFAULT_HOST),
        port=port or int(os.environ.get(PORT_ENV_VAR, str(DEFAULT_PORT))),
        ws_ping_interval=None,
        ws_ping_timeout=None,
    )


@cli.group()
def storage():
    """File-storage maintenance commands (replaces the old `db` group)."""


@storage.command()
def init():
    from server.storage import StorageHome, ensure_materialized, resolve_home

    home = StorageHome(resolve_home())
    ensure_materialized(home)
    click.echo(f"Storage ready: {home.root}")


@storage.command()
def check():
    from server.storage import StorageHome, resolve_home

    home = StorageHome(resolve_home())
    ok = all(
        p.exists()
        for p in (
            home.providers_path,
            home.models_path,
        )
    )
    click.echo(f"Home:   {home.root}")
    click.echo(f"Catalog materialized: {ok}")


@cli.command()
def status():
    from server.config.loader import load_config
    from server.providers.registry import ProviderRegistry

    config = load_config()
    registry = ProviderRegistry.from_config(config.providers, config.active_provider)
    click.echo(f"Active provider: {config.active_provider}")
    click.echo(f"Workspace:       {config.workspace_root}")
    click.echo(f"Storage home:    {config.home_dir}")
    click.echo(f"Providers:       {registry.list_providers()}")
    provider = registry.get(config.active_provider)
    if provider:
        click.echo(f"Model:           {provider.model}")
    else:
        click.echo("Model:           (none)")


@cli.command()
def tools():
    from server.toolkit import (
        build_inventory,
        create_default_registry,
        measure_registry_schema_tokens,
    )

    registry = create_default_registry()
    baseline = measure_registry_schema_tokens(registry)
    inventory = build_inventory(registry, baseline["model"])
    for entry in inventory:
        click.echo(
            f"  {entry.name:20s}  risk={entry.risk_level:6s}  read_only={entry.read_only!s:5s}"
            f"  cap={entry.capability_id:24s}  tokens={entry.schema_tokens:6d}  {entry.description[:60]}"
        )
    click.echo(
        f"\nTotal: {len(inventory)} tools | schema-token baseline: {baseline['total_tokens']}"
        f" ({baseline['model']})"
    )


if __name__ == "__main__":
    cli()
