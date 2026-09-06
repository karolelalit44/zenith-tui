"""HTTP/WebSocket server and entry-point constants.

Owns host/port/endpoint defaults plus the scripted test-WebSocket settings.
Leaf module: no dependency on other constants submodules (only env.py-free).
"""

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
HOST_ENV_VAR = "ZENITH_HOST"
PORT_ENV_VAR = "ZENITH_PORT"
WS_PATH = "/ws"
HEALTH_PATH = "/health"
