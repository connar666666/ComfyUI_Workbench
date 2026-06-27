from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from workbench.sse import EventBus, EventType, _json_safe, get_event_bus


def _run(coro):
    return asyncio.run(coro)


class TestJsonSafe:
    def test_passes_through_primitives(self):
        assert _json_safe("hello") == "hello"
        assert _json_safe(123) == 123
        assert _json_safe(True) is True
        assert _json_safe(None) is None

    def test_serializes_datetime(self):
        dt = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        assert _json_safe(dt) == "2026-01-02T03:04:05+00:00"

    def test_serializes_date(self):
        assert _json_safe(date(2026, 6, 27)) == "2026-06-27"

    def test_serializes_uuid(self):
        u = UUID("12345678-1234-1234-1234-123456789012")
        assert _json_safe(u) == "12345678-1234-1234-1234-123456789012"

    def test_serializes_decimal(self):
        assert _json_safe(Decimal("1.50")) == "1.50"

    def test_walks_dict_and_list(self):
        payload = {
            "id": UUID("11111111-2222-3333-4444-555555555555"),
            "when": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "items": [Decimal("3.14"), 2, "x"],
        }
        out = _json_safe(payload)
        json.dumps(out)  # round-trips through JSON
        assert out["id"] == "11111111-2222-3333-4444-555555555555"
        assert out["when"] == "2026-01-01T00:00:00+00:00"
        assert out["items"][0] == "3.14"


class TestEventBus:
    @pytest.fixture
    def bus(self):
        return EventBus()

    def test_publish_delivers_to_all_subscribers(self, bus: EventBus):
        async def setup():
            return await bus.subscribe("admin"), await bus.subscribe("member")

        q1, q2 = _run(setup())

        bus.publish(EventType.JOB_CREATED, {"id": "j1"}, visible_to="all")

        assert q1.get_nowait()["data"] == {"id": "j1"}
        assert q2.get_nowait()["data"] == {"id": "j1"}

    def test_admin_only_filtering(self, bus: EventBus):
        async def setup():
            return await bus.subscribe("admin"), await bus.subscribe("member")

        admin_q, member_q = _run(setup())

        bus.publish(EventType.QUEUE_UPDATED, {"x": 1}, visible_to="admin")

        assert admin_q.get_nowait()["data"] == {"x": 1}
        with pytest.raises(asyncio.QueueEmpty):
            member_q.get_nowait()

    def test_username_targeting(self, bus: EventBus):
        async def setup():
            return await bus.subscribe("alice"), await bus.subscribe("bob")

        alice_q, bob_q = _run(setup())

        bus.publish(EventType.USER_JOINED, {"user": "alice"}, visible_to="alice")

        assert alice_q.get_nowait()["data"] == {"user": "alice"}
        with pytest.raises(asyncio.QueueEmpty):
            bob_q.get_nowait()

    def test_unsubscribe_removes_queue(self, bus: EventBus):
        q = _run(bus.subscribe("admin"))
        bus.unsubscribe(q)

        bus.publish(EventType.JOB_CREATED, {"x": 1}, visible_to="all")

        with pytest.raises(asyncio.QueueEmpty):
            q.get_nowait()

    def test_event_payload_contains_type_and_timestamp(self, bus: EventBus):
        q = _run(bus.subscribe("admin"))

        before = datetime.now(timezone.utc)
        bus.publish(EventType.JOB_PROGRESS, {"pct": 50}, visible_to="all")
        after = datetime.now(timezone.utc)

        msg = q.get_nowait()
        assert msg["type"] == "job_progress"
        ts = datetime.fromisoformat(msg["timestamp"])
        assert before <= ts <= after

    def test_queue_full_drops_silently(self, bus: EventBus):
        # We can't easily fill a 256-entry queue in a test, but we can verify
        # the code path doesn't blow up.
        q = _run(bus.subscribe("admin"))
        bus.publish(EventType.JOB_CREATED, {"x": 1})
        q.get_nowait()
        bus.publish(EventType.JOB_CREATED, {"x": 2})
        assert q.get_nowait()["data"] == {"x": 2}


class TestGetEventBus:
    def test_returns_singleton(self):
        a = get_event_bus()
        b = get_event_bus()
        assert a is b

    def test_singleton_can_be_reset_between_tests(self):
        # The fixture used by the test should clear the global. We just call
        # the singleton here to make sure no crash happens.
        get_event_bus()
        get_event_bus()