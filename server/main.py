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
def db():
    pass


def _resolve_db_option(db_path: str | None) -> str:
    from server.persistence.connection import resolve_db_path

    return db_path or resolve_db_path()


@db.command()
@click.option("--db-path", default=None, help="Override database path")
def init(db_path: str | None):
    from server.persistence.startup import DatabaseStartupService

    target = _resolve_db_option(db_path)
    result = DatabaseStartupService(target).run()
    click.echo(f"Database ready: mode={result['mode']} version={result['version']} path={target}")


@db.command()
@click.option("--db-path", default=None, help="Override database path")
def migrate(db_path: str | None):
    from server.persistence.startup import DatabaseStartupService

    target = _resolve_db_option(db_path)
    result = DatabaseStartupService(target).run()
    click.echo(
        f"Migrated: mode={result['mode']} version={result['version']} applied={result['applied']}"
    )


@db.command()
@click.option("--db-path", default=None, help="Override database path")
def current(db_path: str | None):
    from server.persistence.startup import get_current_version

    target = _resolve_db_option(db_path)
    version = get_current_version(target)
    click.echo(f"DB: {target}")
    click.echo(f"Current revision: {version or '(not migrated)'}")


@db.command()
@click.option("--db-path", default=None, help="Override database path")
def history(db_path: str | None):
    from server.persistence.migrations import runner

    target = _resolve_db_option(db_path)
    applied = set(runner.get_applied(target))
    click.echo(f"DB: {target}")
    for m in runner.discover():
        state = "applied " if m["version"] in applied else "pending "
        click.echo(f"  [{state}] {m['version']}  {m['title']}  ({m['filename']})")


@db.command()
@click.option("--db-path", default=None, help="Override database path")
def downgrade(db_path: str | None):
    target = _resolve_db_option(db_path)
    click.echo(
        f"Downgrade is not supported. DB: {target} — revert schema changes with a new forward migration instead."
    )


@cli.command()
def status():
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
