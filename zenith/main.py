import click


@click.group()
@click.version_option(package_name="zenith")
def cli():
    """Zenith AI Coding Assistant Backend"""
    pass


@cli.command()
@click.option("--host", default="localhost", help="Host to bind to")
@click.option("--port", default=8765, type=int, help="Port to listen on")
def serve(host: str, port: int):
    """Start the WebSocket server"""
    import uvicorn

    from zenith.transport.server import create_app

    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    cli()
