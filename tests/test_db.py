import pytest
from core.session import Session
from core.message import Message
from db.repository import SessionRepository, MessageRepository


@pytest.mark.asyncio
async def test_session_create_and_get(db):
    repo = SessionRepository(db)
    session = Session(title="Test Session")
    await repo.create(session)
    loaded = await repo.get(session.id)
    assert loaded is not None
    assert loaded.title == "Test Session"
    assert loaded.mode == "build"


@pytest.mark.asyncio
async def test_session_list_active(db):
    repo = SessionRepository(db)
    await repo.create(Session(title="Session 1"))
    await repo.create(Session(title="Session 2"))
    sessions = await repo.list_active()
    assert len(sessions) == 2


@pytest.mark.asyncio
async def test_session_update(db):
    repo = SessionRepository(db)
    session = Session(title="Original")
    await repo.create(session)
    session.title = "Updated"
    await repo.update(session)
    loaded = await repo.get(session.id)
    assert loaded.title == "Updated"


@pytest.mark.asyncio
async def test_session_delete(db):
    repo = SessionRepository(db)
    session = Session(title="To Delete")
    await repo.create(session)
    await repo.delete(session.id)
    assert await repo.get(session.id) is None


@pytest.mark.asyncio
async def test_message_create_and_get(db):
    s_repo = SessionRepository(db)
    m_repo = MessageRepository(db)
    session = Session(title="Test")
    await s_repo.create(session)
    msg = Message(session_id=session.id, role="user", content="Hello")
    await m_repo.create(msg)
    messages = await m_repo.get_by_session(session.id)
    assert len(messages) == 1
    assert messages[0].content == "Hello"
    assert messages[0].role == "user"


@pytest.mark.asyncio
async def test_message_count_tokens(db):
    s_repo = SessionRepository(db)
    m_repo = MessageRepository(db)
    session = Session(title="Test")
    await s_repo.create(session)
    await m_repo.create(Message(session_id=session.id, role="user", content="Hi", token_count=10))
    await m_repo.create(Message(session_id=session.id, role="assistant", content="Hello", token_count=15))
    total = await m_repo.count_tokens(session.id)
    assert total == 25


@pytest.mark.asyncio
async def test_message_with_events(db):
    from core.events import Event, EventKind
    s_repo = SessionRepository(db)
    m_repo = MessageRepository(db)
    session = Session(title="With Events")
    await s_repo.create(session)
    events = [Event(kind=EventKind.MESSAGE, data={"text": "hello"})]
    msg = Message(session_id=session.id, role="assistant", content="hello", events=events)
    await m_repo.create(msg)
    loaded = await m_repo.get_by_session(session.id)
    assert len(loaded) == 1
    assert len(loaded[0].events) == 1
    assert loaded[0].events[0].kind == EventKind.MESSAGE
