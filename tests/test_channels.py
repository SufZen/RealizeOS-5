"""Tests for realize_core.channels — multi-channel gateway."""

import json
import time

import pytest
from realize_core.channels.base import IncomingMessage, OutgoingMessage
from realize_core.channels.scheduler import (
    CronScheduler,
    ScheduledJob,
    get_scheduler,
    parse_interval,
)
from realize_core.channels.web import WebChannel
from realize_core.channels.webhooks import WebhookChannel, WebhookEndpoint
from realize_core.channels.whatsapp import WhatsAppChannel, _split_message

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
            user_id="u1",
            text="hi",
            system_key="biz",
            channel="telegram",
            topic_id="t1",
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
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "contacts": [{"wa_id": "1234", "profile": {"name": "Test"}}],
                                "messages": [
                                    {
                                        "from": "1234",
                                        "type": "text",
                                        "text": {"body": "Hello"},
                                        "id": "msg1",
                                        "timestamp": "1234567890",
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
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
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "contacts": [{"wa_id": "5678", "profile": {"name": "User"}}],
                                "messages": [
                                    {
                                        "from": "5678",
                                        "type": "image",
                                        "image": {
                                            "id": "media123",
                                            "mime_type": "image/jpeg",
                                            "caption": "Look at this",
                                        },
                                        "id": "msg2",
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
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
            name="test",
            system_key="biz",
            message="do something",
            interval_seconds=60,
        )
        assert job.is_due  # Never run, so it's due

    def test_is_due_disabled(self):
        job = ScheduledJob(
            name="test",
            system_key="biz",
            message="do something",
            interval_seconds=60,
            enabled=False,
        )
        assert not job.is_due

    def test_is_due_after_run(self):
        job = ScheduledJob(
            name="test",
            system_key="biz",
            message="do something",
            interval_seconds=3600,
            last_run=time.time(),
        )
        assert not job.is_due

    def test_next_run_in(self):
        job = ScheduledJob(
            name="test",
            system_key="biz",
            message="do something",
            interval_seconds=3600,
            last_run=time.time(),
        )
        assert job.next_run_in > 3500  # Roughly 3600 minus elapsed


class TestCronScheduler:
    def test_add_job(self):
        scheduler = CronScheduler()
        scheduler.add_job(
            ScheduledJob(
                name="test",
                system_key="biz",
                message="hello",
                interval_seconds=60,
            )
        )
        assert scheduler.job_count == 1

    def test_remove_job(self):
        scheduler = CronScheduler()
        scheduler.add_job(
            ScheduledJob(
                name="test",
                system_key="biz",
                message="hello",
                interval_seconds=60,
            )
        )
        assert scheduler.remove_job("test")
        assert scheduler.job_count == 0

    def test_remove_nonexistent(self):
        scheduler = CronScheduler()
        assert not scheduler.remove_job("nope")

    def test_enable_disable(self):
        scheduler = CronScheduler()
        scheduler.add_job(
            ScheduledJob(
                name="test",
                system_key="biz",
                message="hello",
                interval_seconds=60,
            )
        )
        assert scheduler.disable_job("test")
        assert scheduler.enable_job("test")
        assert not scheduler.disable_job("nope")

    def test_status_summary(self):
        scheduler = CronScheduler()
        scheduler.add_job(
            ScheduledJob(
                name="test",
                system_key="biz",
                message="hello",
                interval_seconds=60,
            )
        )
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
        import hashlib
        import hmac as hmac_mod

        secret = "my-secret"
        body = b"test-body"
        expected = hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()

        ep = WebhookEndpoint(name="test", system_key="biz", secret=secret)
        assert ep.verify_signature(body, expected)
        assert not ep.verify_signature(body, "wrong-sig")

    def test_verify_signature_prefixed(self):
        import hashlib
        import hmac as hmac_mod

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
            name="test",
            system_key="biz",
            message_template="Event: {action} on {repo}",
        )
        result = ep.format_payload({"action": "push", "repo": "myrepo"})
        assert result == "Event: push on myrepo"

    def test_format_payload_template_fallback(self):
        ep = WebhookEndpoint(
            name="test",
            system_key="biz",
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
        ch.register_endpoint(
            WebhookEndpoint(
                name="github",
                system_key="biz",
                secret="abc",
            )
        )
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
        ch.register_endpoint(
            WebhookEndpoint(
                name="test",
                system_key="biz",
                enabled=False,
            )
        )
        result = await ch.process_webhook("test", {})
        assert result is None

    @pytest.mark.asyncio
    async def test_process_webhook_bad_signature(self):
        ch = WebhookChannel()
        ch.register_endpoint(
            WebhookEndpoint(
                name="test",
                system_key="biz",
                secret="secret",
            )
        )
        result = await ch.process_webhook(
            "test",
            {"data": "x"},
            body_bytes=b"body",
            signature="wrong",
        )
        assert result is None


# ===========================================================================
# HARDENING TESTS — new tests for audit fixes
# ===========================================================================


class TestMessageIdGeneration:
    """Verify that message_id is auto-generated on IncomingMessage and OutgoingMessage."""

    def test_incoming_message_has_auto_id(self):
        msg = IncomingMessage(user_id="u1", text="hello")
        assert msg.message_id != ""
        assert len(msg.message_id) == 16

    def test_outgoing_message_has_auto_id(self):
        msg = OutgoingMessage(user_id="u1", text="reply")
        assert msg.message_id != ""
        assert len(msg.message_id) == 16

    def test_message_ids_are_unique(self):
        ids = {IncomingMessage(user_id="u1", text="t").message_id for _ in range(100)}
        assert len(ids) == 100  # All IDs should be unique


class TestXssSanitization:
    """Verify _sanitize_text strips XSS vectors."""

    def test_strips_script_tags(self):
        from realize_core.channels.base import _sanitize_text

        assert _sanitize_text("Hello <script>alert(1)</script> world") == "Hello alert(1) world"

    def test_strips_onerror_handler(self):
        from realize_core.channels.base import _sanitize_text

        result = _sanitize_text('<img onerror="alert(1)" src=x>')
        assert "onerror" not in result

    def test_strips_javascript_uri(self):
        from realize_core.channels.base import _sanitize_text

        result = _sanitize_text('Click <a href="javascript:alert(1)">here</a>')
        assert "javascript:" not in result

    def test_safe_text_unchanged(self):
        from realize_core.channels.base import _sanitize_text

        safe = "Hello world! This is *bold* and _italic_ text."
        assert _sanitize_text(safe) == safe


class TestWhatsAppDeduplication:
    """Verify message deduplication in WhatsApp channel."""

    def test_duplicate_message_skipped(self):
        ch = WhatsAppChannel(phone_number_id="123", access_token="tok")
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "contacts": [{"wa_id": "1234", "profile": {"name": "Test"}}],
                                "messages": [
                                    {
                                        "id": "wamid.abc123",
                                        "type": "text",
                                        "from": "1234",
                                        "text": {"body": "Hello"},
                                        "timestamp": "123",
                                    },
                                ],
                            }
                        }
                    ]
                }
            ]
        }

        # First parse — should return 1 message
        msgs1 = ch.parse_webhook(payload)
        assert len(msgs1) == 1

        # Second parse with same payload — should return 0 (deduplicated)
        msgs2 = ch.parse_webhook(payload)
        assert len(msgs2) == 0

    def test_different_messages_not_deduplicated(self):
        ch = WhatsAppChannel(phone_number_id="123", access_token="tok")

        def make_payload(msg_id):
            return {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "contacts": [{"wa_id": "1234", "profile": {"name": "T"}}],
                                    "messages": [
                                        {
                                            "id": msg_id,
                                            "type": "text",
                                            "from": "1234",
                                            "text": {"body": "Hi"},
                                            "timestamp": "1",
                                        },
                                    ],
                                }
                            }
                        ]
                    }
                ]
            }

        msgs1 = ch.parse_webhook(make_payload("id-1"))
        msgs2 = ch.parse_webhook(make_payload("id-2"))
        assert len(msgs1) == 1
        assert len(msgs2) == 1


class TestWhatsAppMessageSplitting:
    """Verify message splitting for WhatsApp 4096-char limit."""

    def test_short_message_not_split(self):
        chunks = _split_message("Hello")
        assert len(chunks) == 1

    def test_long_message_split(self):
        long_text = "A" * 8000
        chunks = _split_message(long_text, max_len=4096)
        assert len(chunks) >= 2
        assert all(len(c) <= 4096 for c in chunks)
        assert "".join(chunks) == long_text

    def test_splits_at_newlines(self):
        text = ("Line1\n" * 800).strip()  # ~4800 chars
        chunks = _split_message(text, max_len=4096)
        assert len(chunks) >= 2
        # Second chunk should start with "Line1" (not mid-word)
        assert chunks[1].startswith("Line1")


class TestTelegramMessageSplitting:
    """Verify message splitting for Telegram."""

    def test_telegram_split_function(self):
        from realize_core.channels.telegram import _split_telegram_message

        short = _split_telegram_message("Hello")
        assert len(short) == 1

        long_text = "Word " * 1000  # ~5000 chars
        chunks = _split_telegram_message(long_text)
        assert len(chunks) >= 2
        assert all(len(c) <= 4096 for c in chunks)


class TestWebhookReplayPrevention:
    """Verify replay-attack prevention in webhook channel."""

    @pytest.mark.asyncio
    async def test_stale_timestamp_rejected(self):
        ch = WebhookChannel()
        ch.register_endpoint(WebhookEndpoint(name="test", system_key="biz"))

        # Timestamp 10 minutes old (past tolerance)
        stale_ts = time.time() - 600
        result = await ch.process_webhook("test", {"data": "x"}, timestamp=stale_ts)
        assert result is None

    @pytest.mark.asyncio
    async def test_duplicate_nonce_rejected(self):
        ch = WebhookChannel()
        ch.register_endpoint(WebhookEndpoint(name="test", system_key="biz"))

        # First delivery with nonce
        # (will fail at handle_incoming since no engine, but passes validation)
        try:
            await ch.process_webhook("test", {"data": "x"}, nonce="delivery-123")
        except Exception:
            pass  # Expected — no engine connected

        # Second delivery with same nonce — should be rejected before handle_incoming
        result = await ch.process_webhook("test", {"data": "x"}, nonce="delivery-123")
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_signature_rejected_when_secret_set(self):
        ch = WebhookChannel()
        ch.register_endpoint(WebhookEndpoint(name="secure", system_key="biz", secret="my-secret"))

        # No signature provided → should reject
        result = await ch.process_webhook("secure", {"data": "x"}, body_bytes=b"body")
        assert result is None


class TestWebhookHealthCheck:
    """Verify webhook health_check works."""

    def test_health_check_structure(self):
        ch = WebhookChannel()
        ch.register_endpoint(WebhookEndpoint(name="test", system_key="biz"))
        health = ch.health_check()
        assert health["name"] == "webhook"
        assert health["healthy"] is True
        assert health["details"]["total_endpoints"] == 1


class TestSchedulerCircuitBreaker:
    """Verify scheduler circuit breaker auto-disables failing jobs."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_disables_after_failures(self):
        scheduler = CronScheduler()
        job = ScheduledJob(
            name="failing-job",
            system_key="biz",
            message="fail",
            interval_seconds=60,
        )
        scheduler.add_job(job)

        # Set handler that always fails
        async def failing_handler(**kwargs):
            raise RuntimeError("Simulated failure")

        scheduler.set_handler(failing_handler)

        # Run the job 5 times (MAX_CONSECUTIVE_FAILURES)
        for _ in range(5):
            await scheduler._execute_job(job)

        # Job should be auto-disabled
        assert job.enabled is False
        assert job.consecutive_failures >= 5
        assert job.last_error != ""

    @pytest.mark.asyncio
    async def test_circuit_breaker_resets_on_success(self):
        scheduler = CronScheduler()
        job = ScheduledJob(
            name="test-job",
            system_key="biz",
            message="ok",
            interval_seconds=60,
        )
        scheduler.add_job(job)
        job.consecutive_failures = 3
        job.last_error = "old error"

        async def success_handler(**kwargs):
            pass

        scheduler.set_handler(success_handler)
        await scheduler._execute_job(job)

        assert job.consecutive_failures == 0
        assert job.last_error == ""


class TestSchedulerStatePersistence:
    """Verify scheduler can save and load state."""

    def test_save_and_load_state(self, tmp_path):
        # Create scheduler with a job
        s1 = CronScheduler()
        job = ScheduledJob(
            name="persist-test",
            system_key="biz",
            message="hello",
            interval_seconds=3600,
        )
        job.run_count = 42
        job.consecutive_failures = 2
        job.last_error = "some error"
        job.last_run = 1000.0
        s1.add_job(job)

        state_file = tmp_path / "scheduler_state.json"
        s1.save_state(state_file)

        # Create new scheduler, add same job, load state
        s2 = CronScheduler()
        s2.add_job(
            ScheduledJob(
                name="persist-test",
                system_key="biz",
                message="hello",
                interval_seconds=3600,
            )
        )
        s2.load_state(state_file)

        loaded_job = s2._jobs["persist-test"]
        assert loaded_job.run_count == 42
        assert loaded_job.consecutive_failures == 2
        assert loaded_job.last_error == "some error"
        assert loaded_job.last_run == 1000.0


class TestSchedulerHealthCheck:
    """Verify scheduler health_check."""

    def test_health_check_not_running(self):
        s = CronScheduler()
        health = s.health_check()
        assert health["name"] == "scheduler"
        assert health["healthy"] is False  # Not running

    def test_health_check_shows_failing_jobs(self):
        s = CronScheduler()
        job = ScheduledJob(name="bad", system_key="biz", message="x", interval_seconds=60)
        job.consecutive_failures = 3
        s.add_job(job)

        health = s.health_check()
        assert "bad" in health["details"]["failing_jobs"]


class TestWhatsAppHealthCheck:
    def test_unconfigured_not_healthy(self):
        ch = WhatsAppChannel()
        health = ch.health_check()
        assert health["healthy"] is False

    def test_configured_healthy(self):
        ch = WhatsAppChannel(phone_number_id="123", access_token="tok")
        health = ch.health_check()
        assert health["healthy"] is True
        assert health["details"]["dedup_cache_size"] == 0
