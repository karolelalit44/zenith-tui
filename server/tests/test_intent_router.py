from __future__ import annotations

from server.toolkit.router import IntentKind, IntentRouter


def test_intent_router_greetings():
    router = IntentRouter()

    res1 = router.classify("hello")
    assert res1.kind == IntentKind.DIRECT_RESPONSE
    assert res1.confidence == 1.0

    res2 = router.classify("Hi!")
    assert res2.kind == IntentKind.DIRECT_RESPONSE
    assert res2.confidence == 1.0

    res3 = router.classify("who are you?")
    assert res3.kind == IntentKind.DIRECT_RESPONSE
    assert res3.confidence == 1.0


def test_intent_router_mutations():
    router = IntentRouter()

    res1 = router.classify("Fix the bug in main.py")
    assert res1.kind == IntentKind.EXECUTION_MUTATION
    assert res1.confidence >= 0.9

    res2 = router.classify("Create a new script scripts/test.py")
    assert res2.kind == IntentKind.EXECUTION_MUTATION
    assert res2.confidence >= 0.9


def test_intent_router_discovery():
    router = IntentRouter()

    res1 = router.classify("Where is SessionRepository defined?")
    assert res1.kind == IntentKind.READ_ONLY_DISCOVERY
    assert res1.confidence >= 0.8
