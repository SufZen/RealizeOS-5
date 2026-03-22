"""Tests for realize_core.channels — multi-channel gateway."""
import json
import pytest
import time

from realize_core.channels.base import BaseChannel, IncomingMessage, OutgoingMessage
from realize_core.channels.whatsapp import WhatsAppChannel, _split_message
from realize_core.channels.web import WebChannel, WebSocketClient
from realize_core.channels.scheduler import (
    CronScheduler,
    ScheduledJob,
    parse_interval,
    get_scheduler,
)
from realize_core.channels.webhooks import WebhookChannel, WebhookEndpoint


# ===========================================================================
# Base Channel tests
# ===========================================================================


class TestIncomingMessage:
    def test_defaults(self):
        msg = IncomingMessage(user_id="u1", text="hello")
        assert msg.channel == "api"
        assert msg.image_data == b""
        assert msg.metadata == {}

    def test_all_fields(self):
        msg = IncomingMessage(
            user_id="u1", text="hi", system_key="biz",
            channel="telegram", topic_id="t1",
            metadata={"chat_id": 123},
        )
        assert msg.system_key == "biz"
        assert msg.metadata["chat_id"] == 123


class TestOutgoingMessage:
    def test_defaults(self):
        msg = OutgoingMessage(text="response", user_id="u1")
        assert msg.channel == "api"
        assert msg.files == []


# ===========================================================================
# WhatsApp Channel tests
# ===========================================================================


class TestWhatsAppChannel:
    def test_init_defaults(self):
        ch = WhatsAppChannel()
        assert ch.channel_name == "whatsapp"
        assert ch.verify_token == "realize-os"

    def test_format_instructions(self):
        ch = WhatsAppChannel()
        instructions = ch.format_instructions()
        assert "WhatsApp" in instructions
        assert "4096" in instructions

    def test_verify_webhook_success(self):
        ch = WhatsAppChannel(verify_token="test-token")
        result = ch.verify_webhook("subscribe", "test-token", "challenge123")
        assert result == "challenge123"

    def test_verify_webhook_fail(self):
        ch = WhatsAppChannel(verify_token="test-token")
        result = ch.verify_webhook("subscribe", "wrong-token", "challenge123")
        assert result is None

    def test_parse_webhook_text_message(self):
        ch = WhatsAppChannel()
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{"wa_id": "1234", "profile": {"name": "Test"}}],
                        "messages": [{
                            "from": "1234",
                            "type": "text",
                            "text": {"body": "Hello"},
                            "id": "msg1",
                            "timestamp": "1234567890",
                        }],
                    }
                }]
            }]
        }
        messages = ch.parse_webhook(payload)
        assert len(messages) == 1
        assert messages[0].text == "Hello"
        assert messages[0].user_id == "1234"
        assert messages[0].channel == "whatsapp"
        assert messages[0].metadata["contact_name"] == "Test"

    def test_parse_webhook_image_message(self):
        ch = WhatsAppChannel()
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{"wa_id": "5678", "profile": {"name": "User"}}],
                        "messages": [{
                            "from": "5678",
                            "type": "image",
                            "image": {
                                "id": "media123",
                                "mime_type": "image/jpeg",
                                "caption": "Look at this",
                            },
                            "id": "msg2",
                        }],
                    }
                }]
            }]
        }
        messages = ch.parse_webhook(payload)
        assert len(messages) == 1
        assert messages[0].text == "Look at this"
        assert messages[0].image_media_type == "image/jpeg"

    def test_parse_webhook_empty(self):
        ch = WhatsAppChannel()
        messages = ch.parse_webhook({"entry": []})
        assert messages == []

    def test_parse_webhook_no_messages(self):
        ch = WhatsAppChannel()
        payload = {"entry": [{"changes": [{"value": {"statuses": [{}]}}]}]}
        messages = ch.parse_webhook(payload)
        assert messages == []


class TestSplitMessage:
    def test_short_message(self):
        assert _split_message("hello") == ["hello"]

    def test_exact_limit(self):
        text = "a" * 4096
        assert _split_message(text) == [text]

    def test_long_message_splits(self):
        text = "word " * 1000  # ~5000 chars
        chunks = _split_message(text, max_len=100)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 100


# ===========================================================================
# Web Channel tests
# ===========================================================================


class TestWebChannel:
    def test_init(self):
        ch = WebChannel()
        assert ch.channel_name == "web"
        assert ch.connected_clients == 0

    def test_format_instructions(self):
        ch = WebChannel()
        assert "markdown" in ch.format_instructions().lower()

    @pytest.mark.asyncio
    async def test_connect_client(self):
        ch = WebChannel()
        sent = []

        async def mock_send(data):
            sent.append(data)

        cid = await ch.connect_client("user1", mock_send)
        assert ch.connected_clients == 1
        info = ch.get_client_info(cid)
        assert info["user_id"] == "user1"

    @pytest.mark.asyncio
    async def test_disconnect_client(self):
        ch = WebChannel()

        async def mock_send(data):
            pass

        cid = await ch.connect_client("user1", mock_send)
        assert ch.connected_clients == 1
        await ch.disconnect_client(cid)
        assert ch.connected_clients == 0

    @pytest.mark.asyncio
    async def test_handle_ws_ping(self):
        ch = WebChannel()

        async def mock_send(data):
            pass

        cid = await ch.connect_client("user1", mock_send)
        result = await ch.handle_ws_message(cid, '{"type": "ping"}')
        data = json.loads(result)
        assert data["type"] == "pong"

    @pytest.mark.asyncio
    async def test_handle_ws_unknown_client(self):
        ch = WebChannel()
        result = await ch.handle_ws_message("nonexistent", '{"type": "ping"}')
        data = json.loads(result)
        assert data["type"] == "error"

    @pytest.mark.asyncio
    async def test_handle_ws_invalid_json(self):
        ch = WebChannel()

        async def mock_send(data):
            pass

        cid = await ch.connect_client("user1", mock_send)
        result = await ch.handle_ws_message(cid, "not json")
        data = json.loads(result)
        assert data["type"] == "error"

    def test_get_client_info_nonexistent(self):
        ch = WebChannel()
        assert ch.get_client_info("nope") is None


# ===========================================================================
# Scheduler tests
# ===========================================================================


class TestParseInterval:
    def test_shortcuts(self):
        assert parse_interval("1m") == 60
        assert parse_interval("5m") == 300
        assert parse_interval("1h") == 3600
        assert parse_interval("daily") == 86400
        assert parse_interval("weekly") == 604800

    def test_raw_seconds(self):
        assert parse_interval("120") == 120

    def test_unknown_defaults_to_1h(self):
        assert parse_interval("random") == 3600

    def test_case_insensitive(self):
        assert parse_interval("Daily") == 86400
        assert parse_interval("1H") == 3600


class TestScheduledJob:
    def test_is_due_when_never_run(self):
        job = ScheduledJob(
            name="test", system_key="biz",
            message="do something", interval_seconds=60,
        )
        assert job.is_due  # Never run, so it's due

    def test_is_due_disabled(self):
        job = ScheduledJob(
            name="test", system_key="biz",
            message="do something", interval_seconds=60,
            enabled=False,
        )
        assert not job.is_due

    def test_is_due_after_run(self):
        job = ScheduledJob(
            name="test", system_key="biz",
            message="do something", interval_seconds=3600,
            last_run=time.time(),
        )
        assert not job.is_due

    def test_next_run_in(self):
        job = ScheduledJob(
            name="test", system_key="biz",
            message="do something", interval_seconds=3600,
            last_run=time.time(),
        )
        assert job.next_run_in > 3500  # Roughly 3600 minus elapsed


class TestCronScheduler:
    def test_add_job(self):
        scheduler = CronScheduler()
        scheduler.add_job(ScheduledJob(
            name="test", system_key="biz",
            message="hello", interval_seconds=60,
        ))
        assert scheduler.job_count == 1

    def test_remove_job(self):
        scheduler = CronScheduler()
        scheduler.add_job(ScheduledJob(
            name="test", system_key="biz",
            message="hello", interval_seconds=60,
        ))
        assert scheduler.remove_job("test")
        assert scheduler.job_count == 0

    def test_remove_nonexistent(self):
        scheduler = CronScheduler()
        assert not scheduler.remove_job("nope")

    def test_enable_disable(self):
        scheduler = CronScheduler()
        scheduler.add_job(ScheduledJob(
            name="test", system_key="biz",
            message="hello", interval_seconds=60,
        ))
        assert scheduler.disable_job("test")
        assert scheduler.enable_job("test")
        assert not scheduler.disable_job("nope")

    def test_status_summary(self):
        scheduler = CronScheduler()
        scheduler.add_job(ScheduledJob(
            name="test", system_key="biz",
            message="hello", interval_seconds=60,
        ))
        summary = scheduler.status_summary()
        assert summary["total_jobs"] == 1
        assert "test" in summary["jobs"]


class TestSchedulerSingleton:
    def test_singleton(self):
        import realize_core.channels.scheduler as mod
        mod._scheduler = None
        s1 = get_scheduler()
        s2 = get_scheduler()
        assert s1 is s2
        mod._scheduler = None


# ===========================================================================
# Webhook tests
# ===========================================================================


class TestWebhookEndpoint:
    def test_verify_signature_no_secret(self):
        ep = WebhookEndpoint(name="test", system_key="biz")
        assert ep.verify_signature(b"body", "any-sig")

    def test_verify_signature_with_secret(self):
        import hashlib, hmac as hmac_mod
        secret = "my-secret"
        body = b"test-body"
        expected = hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()

        ep = WebhookEndpoint(name="test", system_key="biz", secret=secret)
        assert ep.verify_signature(body, expected)
        assert not ep.verify_signature(body, "wrong-sig")

    def test_verify_signature_prefixed(self):
        import hashlib, hmac as hmac_mod
        secret = "my-secret"
        body = b"test-body"
        expected = "sha256=" + hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()

        ep = WebhookEndpoint(name="test", system_key="biz", secret=secret)
        assert ep.verify_signature(body, expected)

    def test_format_payload_default(self):
        ep = WebhookEndpoint(name="github", system_key="biz")
        result = ep.format_payload({"action": "push", "repo": "test"})
        assert "github" in result
        assert "push" in result

    def test_format_payload_template(self):
        ep = WebhookEndpoint(
            name="test", system_key="biz",
            message_template="Event: {action} on {repo}",
        )
        result = ep.format_payload({"action": "push", "repo": "myrepo"})
        assert result == "Event: push on myrepo"

    def test_format_payload_template_fallback(self):
        ep = WebhookEndpoint(
            name="test", system_key="biz",
            message_template="Event: {missing_key}",
        )
        # Should fall back to default format when template fails
        result = ep.format_payload({"action": "push"})
        assert "test" in result  # Falls back to summary format


class TestWebhookChannel:
    def test_init(self):
        ch = WebhookChannel()
        assert ch.channel_name == "webhook"
        assert ch.endpoint_count == 0

    def test_register_endpoint(self):
        ch = WebhookChannel()
        ch.register_endpoint(WebhookEndpoint(name="test", system_key="biz"))
        assert ch.endpoint_count == 1
        assert ch.get_endpoint("test") is not None

    def test_unregister_endpoint(self):
        ch = WebhookChannel()
        ch.register_endpoint(WebhookEndpoint(name="test", system_key="biz"))
        assert ch.unregister_endpoint("test")
        assert ch.endpoint_count == 0

    def test_status_summary(self):
        ch = WebhookChannel()
        ch.register_endpoint(WebhookEndpoint(
            name="github", system_key="biz", secret="abc",
        ))
        summary = ch.status_summary()
        assert summary["total_endpoints"] == 1
        assert summary["endpoints"]["github"]["has_secret"]

    @pytest.mark.asyncio
    async def test_process_webhook_unknown_endpoint(self):
        ch = WebhookChannel()
        result = await ch.process_webhook("unknown", {})
        assert result is None

    @pytest.mark.asyncio
    async def test_process_webhook_disabled(self):
        ch = WebhookChannel()
        ch.register_endpoint(WebhookEndpoint(
            name="test", system_key="biz", enabled=False,
        ))
        result = await ch.process_webhook("test", {})
        assert result is None

    @pytest.mark.asyncio
    async def test_process_webhook_bad_signature(self):
        ch = WebhookChannel()
        ch.register_endpoint(WebhookEndpoint(
            name="test", system_key="biz", secret="secret",
        ))
        result = await ch.process_webhook(
            "test", {"data": "x"},
            body_bytes=b"body", signature="wrong",
        )
        assert result is None
