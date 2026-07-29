"""Application container — dependency injection wiring for all services."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from agent.context import ContextManager
from agent.coordinator import CoordinatorService, DefaultCoordinator
from agent.runtime import AgentRuntime, DefaultAgentRuntime
from config.settings import AppSettings
from core.events import AsyncEventBus, EventBus
from db.connection import Database
from db.repository import MessageRepository, SessionRepository
from providers.base import BaseProvider
from providers.registry import ProviderRegistry
from session.service import DefaultSessionService, SessionService
from tools import create_default_registry
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class AppContainer:
    """Wires together all application services.

    Usage:
        container = AppContainer.create(config)
        await container.start()
        ...
        await container.stop()
    """

    # Config
    config: AppSettings

    # Infrastructure
    db: Database = field(default=None)  # type: ignore[assignment]
    event_bus: EventBus = field(default=None)  # type: ignore[assignment]

    # Repos
    session_repo: SessionRepository = field(default=None)  # type: ignore[assignment]
    message_repo: MessageRepository = field(default=None)  # type: ignore[assignment]

    # Providers
    provider_registry: ProviderRegistry = field(default=None)  # type: ignore[assignment]
    active_provider: BaseProvider | None = None

    # Tools
    tool_registry: ToolRegistry = field(default=None)  # type: ignore[assignment]

    # Agent
    runtime: AgentRuntime = field(default=None)  # type: ignore[assignment]
    coordinator: CoordinatorService = field(default=None)  # type: ignore[assignment]
    context_manager: ContextManager = field(default=None)  # type: ignore[assignment]

    # Session service
    session_service: SessionService = field(default=None)  # type: ignore[assignment]

    @classmethod
    def create(cls, config: AppSettings) -> AppContainer:
        """Create a container with all services wired (but not started)."""
        container = cls(config=config)
        container._wire()
        return container

    def _wire(self) -> None:
        """Wire all dependencies."""
        # EventBus
        self.event_bus = AsyncEventBus()

        # Provider registry
        self.provider_registry = ProviderRegistry.from_config(
            self.config.providers, self.config.active_provider
        )
        self.active_provider = self.provider_registry.get(self.config.active_provider)
        logger.info(
            "Provider registry wired: active=%s, available=%s",
            self.config.active_provider,
            self.provider_registry.list_providers(),
        )

        # Tool registry
        self.tool_registry = create_default_registry(
            timeout=self.config.tools.max_bash_timeout,
            provider=self.active_provider,
        )
        logger.info("Tool registry wired: %d tools", len(self.tool_registry.list_tools()))

        # Context manager
        self.context_manager = ContextManager(self.config)

        # Agent runtime
        self.runtime = DefaultAgentRuntime(
            config=self.config,
            provider=self.active_provider,
            tool_registry=self.tool_registry,
        )

        # Session service (will be wired with DB repos in start())
        # Placeholder — replaced in start()
        self.session_service = _StubSessionService()

        # Coordinator
        self.coordinator = DefaultCoordinator(
            session_service=self.session_service,
            runtime=self.runtime,
        )

    async def start(self) -> None:
        """Start infrastructure (DB, repos, etc.)."""
        # Database
        from db.connection import resolve_db_path
        self.db = Database(resolve_db_path())
        await self.db.connect()
        logger.info("Database connected")

        # Repos
        self.session_repo = SessionRepository(self.db)
        self.message_repo = MessageRepository(self.db)

        # Seed provider catalog
        from db.repository import ProviderRepositoryDB
        provider_repo = ProviderRepositoryDB(self.db)
        await provider_repo.ensure_seeded()

        # Wire session service with real repos
        self.session_service = DefaultSessionService(
            session_repo=self.session_repo,
            message_repo=self.message_repo,
            event_bus=self.event_bus,
        )

        # Re-wire coordinator with real session service
        self.coordinator = DefaultCoordinator(
            session_service=self.session_service,
            runtime=self.runtime,
        )

        logger.info("Application container started")

    async def stop(self) -> None:
        """Stop infrastructure."""
        if self.db:
            await self.db.close()
            logger.info("Database closed")
        self.db = None

    def reload_config(self) -> None:
        """Hot-reload configuration (e.g. after setup wizard)."""
        from config.loader import load_config
        self.config = load_config()
        self.provider_registry = ProviderRegistry.from_config(
            self.config.providers, self.config.active_provider
        )
        self.active_provider = self.provider_registry.get(self.config.active_provider)
        self.context_manager = ContextManager(self.config)
        self.runtime = DefaultAgentRuntime(
            config=self.config,
            provider=self.active_provider,
            tool_registry=self.tool_registry,
        )
        logger.info("Config reloaded: provider=%s", self.config.active_provider)


class _StubSessionService(SessionService):
    """Placeholder session service until DB is available."""

    async def create(self, title=None, mode=None):
        raise RuntimeError("Container not started — call await container.start()")

    async def get(self, session_id):
        raise RuntimeError("Container not started")

    async def require(self, session_id):
        raise RuntimeError("Container not started")

    async def list_active(self):
        return []

    async def add_message(self, session_id, message):
        raise RuntimeError("Container not started")

    async def get_history(self, session_id, limit=None):
        return []

    async def get_message_count(self, session_id):
        return 0

    async def get_token_count(self, session_id):
        return 0

    async def update_title(self, session_id, title):
        raise RuntimeError("Container not started")

    async def archive(self, session_id):
        raise RuntimeError("Container not started")

    async def delete(self, session_id):
        raise RuntimeError("Container not started")

    async def export_markdown(self, session_id):
        raise RuntimeError("Container not started")
