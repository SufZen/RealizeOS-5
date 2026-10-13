"""Regression for an order-dependent failure of tests/e2e/test_webinar_flow.py.

``realize_core.base_handler`` binds the conversation helpers by name when it
is first imported. The approval tests stub ``conversation.add_message`` to
capture posted messages; when one of them was the first to import
``base_handler``, the stub stayed bound after the test, so a later test that
chats through ``process_message`` stored no history (the webinar API test
then found an empty conversation). The root conftest now starts every test
with the real helpers. These two tests run in file order.
"""

from __future__ import annotations


def test_a_stub_left_on_base_handler_by_an_earlier_test(monkeypatch):
    """What a first import under a patched conversation module leaves behind."""
    import realize_core.base_handler as bh
    from realize_core.memory import conversation

    monkeypatch.setattr(conversation, "add_message", lambda *a, **k: None)
    bh.add_message = conversation.add_message  # bound at import, not undone by monkeypatch
    bh.get_history = lambda *a, **k: []


def test_the_next_test_gets_the_real_conversation_helpers():
    import realize_core.base_handler as bh
    from realize_core.memory import conversation

    assert bh.add_message is conversation.add_message
    assert bh.get_history is conversation.get_history
    assert bh.to_llm_messages is conversation.to_llm_messages
