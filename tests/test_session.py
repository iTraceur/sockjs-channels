import asyncio
from datetime import datetime, timedelta
from unittest import mock

from django.test import TestCase

from sockjs import protocol, Session, SessionIsClosed, SessionIsAcquired
from sockjs.session import DEFAULT_SESSION_TIMEOUT
from .utils import make_handler, make_session, make_manager, make_scope


class TestSession(TestCase):
    @mock.patch("sockjs.session.datetime")
    async def test_ctor(self, mock_datetime):
        now = mock_datetime.now.return_value = datetime.now()

        session = make_session(name="id")

        self.assertEqual(session.id, "id")
        self.assertFalse(session.expired)
        self.assertEqual(session.expires, now + DEFAULT_SESSION_TIMEOUT)

        self.assertEqual(session._hits, 0)
        self.assertEqual(session._heartbeats, 0)
        self.assertEqual(session.state, protocol.STATE_NEW)

        session = make_session(name="id", timeout=timedelta(seconds=15))

        self.assertEqual(session.id, "id")
        self.assertFalse(session.expired)
        self.assertEqual(session.expires, now + timedelta(seconds=15))

    async def test_str(self):
        session = make_session()
        session.state = protocol.STATE_OPEN

        self.assertEqual(str(session), "id='test' connected")

        session._hits = 10
        session._heartbeats = 50
        session.state = protocol.STATE_CLOSING
        self.assertEqual(str(session), "id='test' disconnected hits=10 heartbeats=50")

        session._feed(protocol.FRAME_MESSAGE, "msg")
        self.assertEqual(str(session), "id='test' disconnected queue[1] hits=10 heartbeats=50")

        session.state = protocol.STATE_CLOSED
        self.assertEqual(str(session), "id='test' closed queue[1] hits=10 heartbeats=50")

        session.state = protocol.STATE_OPEN
        session.acquired = True
        self.assertEqual(str(session), "id='test' connected acquired queue[1] hits=10 heartbeats=50")

    @mock.patch("sockjs.session.datetime")
    async def test_tick(self, mock_datetime):
        now = mock_datetime.now.return_value = datetime.now()
        session = make_session()
        self.assertEqual(session.expires, now + session.timeout)

        now = mock_datetime.now.return_value = now + timedelta(hours=1)
        session._tick()
        self.assertEqual(session.expires, now + session.timeout)

    @mock.patch("sockjs.session.datetime")
    async def test_tick_different_timeout(self, mock_datetime):
        now = mock_datetime.now.return_value = datetime.now()
        session = make_session(name="test", timeout=timedelta(seconds=20))

        now = mock_datetime.now.return_value = now + timedelta(hours=1)
        session._tick()
        self.assertEqual(session.expires, now + timedelta(seconds=20))

    @mock.patch("sockjs.session.datetime")
    async def test_tick_custom(self, mock_datetime):
        now = mock_datetime.now.return_value = datetime.now()
        session = make_session(name="test", timeout=timedelta(seconds=20))

        now = mock_datetime.now.return_value = now + timedelta(hours=1)
        session._tick(timedelta(seconds=30))
        self.assertEqual(session.expires, now + timedelta(seconds=30))

    async def test_heartbeat(self):
        session = make_session()
        session.state = protocol.STATE_OPEN
        self.assertEqual(session._heartbeats, 0)
        session._heartbeat()
        await session.wait()
        self.assertEqual(session._heartbeats, 1)
        session._heartbeat()
        await session.wait()
        self.assertEqual(session._heartbeats, 2)

    async def test_heartbeat_consumer(self):
        session = make_session()
        session.state = protocol.STATE_OPEN
        session._heartbeat_consumer = True
        session._heartbeat()
        self.assertEqual(list(session._queue), [(protocol.FRAME_HEARTBEAT, protocol.FRAME_HEARTBEAT)])

    async def test_expire(self):
        session = make_session()
        self.assertFalse(session.expired)

        session.expire()
        self.assertTrue(session.expired)

    async def test_send(self):
        session = make_session()
        session.send("message")

        self.assertEqual(list(session._queue), [])

        session.state = protocol.STATE_OPEN
        session.send("message")

        self.assertEqual(list(session._queue), [(protocol.FRAME_MESSAGE, ["message"])])

    async def test_send_non_str(self):
        session = make_session()
        with self.assertRaises(AssertionError):
            session.send(b"str")

    async def test_send_frame(self):
        session = make_session()
        session.send_frame('a["message"]')

        self.assertEqual(list(session._queue), [])

        session.state = protocol.STATE_OPEN
        session.send_frame('a["message"]')

        self.assertEqual(list(session._queue), [(protocol.FRAME_MESSAGE_BLOB, 'a["message"]')])

    async def test_feed(self):
        session = make_session()
        session._feed(protocol.FRAME_OPEN, protocol.FRAME_OPEN)
        session._feed(protocol.FRAME_MESSAGE, "msg")
        session._feed(protocol.FRAME_CLOSE, (3001, "reason"))

        queue_data = [
            (protocol.FRAME_OPEN, protocol.FRAME_OPEN),
            (protocol.FRAME_MESSAGE, ["msg"]),
            (protocol.FRAME_CLOSE, (3001, "reason")),
        ]

        self.assertEqual(list(session._queue), queue_data)

    async def test_feed_msg_packing(self):
        session = make_session()
        session._feed(protocol.FRAME_MESSAGE, "msg1")
        session._feed(protocol.FRAME_MESSAGE, "msg2")
        session._feed(protocol.FRAME_CLOSE, (3001, "reason"))
        session._feed(protocol.FRAME_MESSAGE, "msg3")

        queue_data = [
            (protocol.FRAME_MESSAGE, ["msg1", "msg2"]),
            (protocol.FRAME_CLOSE, (3001, "reason")),
            (protocol.FRAME_MESSAGE, ["msg3"]),
        ]

        self.assertEqual(list(session._queue), queue_data)

    async def test_feed_with_waiter(self):
        session = make_session()
        loop = asyncio.get_event_loop()
        session._waiter = waiter = loop.create_future()
        session._feed(protocol.FRAME_MESSAGE, "msg")

        self.assertEqual(list(session._queue), [(protocol.FRAME_MESSAGE, ["msg"])])
        self.assertIsNone(session._waiter)
        self.assertTrue(waiter.done())

    async def test_wait(self):
        session = make_session()
        session.state = protocol.STATE_OPEN

        async def send():
            await asyncio.sleep(0.001)
            session._feed(protocol.FRAME_MESSAGE, "msg1")

        asyncio.ensure_future(send())
        frame, payload = await session.wait()
        self.assertEqual(frame, protocol.FRAME_MESSAGE)
        self.assertEqual(payload, 'a["msg1"]')

    async def test_wait_closed(self):
        session = make_session()
        session.state = protocol.STATE_CLOSED
        with self.assertRaises(SessionIsClosed):
            await session.wait()

    async def test_wait_message(self):
        session = make_session()
        session.state = protocol.STATE_OPEN
        session._feed(protocol.FRAME_MESSAGE, "msg1")
        frame, payload = await session.wait()
        self.assertEqual(frame, protocol.FRAME_MESSAGE)
        self.assertEqual(payload, 'a["msg1"]')

    async def test_wait_close(self):
        session = make_session()
        session.state = protocol.STATE_OPEN
        session._feed(protocol.FRAME_CLOSE, (3000, "Go away!"))
        frame, payload = await session.wait()
        self.assertEqual(frame, protocol.FRAME_CLOSE)
        self.assertEqual(payload, 'c[3000,"Go away!"]')

    async def test_wait_message_unpack(self):
        session = make_session()
        session.state = protocol.STATE_OPEN
        session._feed(protocol.FRAME_MESSAGE, "msg1")
        frame, payload = await session.wait(pack=False)
        self.assertEqual(frame, protocol.FRAME_MESSAGE)
        self.assertEqual(payload, ["msg1"])

    async def test_wait_close_unpack(self):
        session = make_session()
        session.state = protocol.STATE_OPEN
        session._feed(protocol.FRAME_CLOSE, (3000, "Go away!"))
        frame, payload = await session.wait(pack=False)
        self.assertEqual(frame, protocol.FRAME_CLOSE)
        self.assertEqual(payload, (3000, "Go away!"))

    async def test_close(self):
        session = make_session()
        session.state = protocol.STATE_OPEN
        session.close()
        self.assertEqual(session.state, protocol.STATE_CLOSING)
        self.assertEqual(list(session._queue), [(protocol.FRAME_CLOSE, (3000, "Go away!"))])

    async def test_close_idempotent(self):
        session = make_session()
        session.state = protocol.STATE_CLOSED
        session.close()
        self.assertEqual(session.state, protocol.STATE_CLOSED)
        self.assertEqual(list(session._queue), [])

    async def test_acquire_new_session(self):
        manager = object()
        messages = []

        session = make_session(result=messages)
        self.assertEqual(session.state, protocol.STATE_NEW)

        scope = make_scope("GET", path="/sockjs/000/000000/test")
        await session.acquire(scope, manager)
        self.assertEqual(session.state, protocol.STATE_OPEN)
        self.assertIs(session.manager, manager)
        self.assertTrue(session._heartbeat_consumer)
        self.assertEqual(list(session._queue), [(protocol.FRAME_OPEN, protocol.FRAME_OPEN)])
        self.assertEqual(messages, [(protocol.OpenMessage, session)])

    async def test_acquire_exception_in_handler(self):
        async def handler(scope, msg, s):
            raise ValueError

        session = make_session(handler=handler)
        self.assertEqual(session.state, protocol.STATE_NEW)

        scope = make_scope("GET", path="/sockjs/000/000000/test")
        await session.acquire(scope, object())
        self.assertEqual(session.state, protocol.STATE_CLOSING)
        self.assertTrue(session._heartbeat_consumer)
        self.assertTrue(session.interrupted)
        queue_data = [
            (protocol.FRAME_OPEN, protocol.FRAME_OPEN),
            (protocol.FRAME_CLOSE, (3000, "Internal error")),
        ]
        self.assertEqual(list(session._queue), queue_data)

    async def test_remote_close(self):
        messages = []
        session = make_session(result=messages)

        await session.remote_close()
        self.assertFalse(session.interrupted)
        self.assertEqual(session.state, protocol.STATE_CLOSING)
        self.assertEqual(messages, [(protocol.SockjsMessage(protocol.MSG_CLOSE, None), session)])

    async def test_remote_close_idempotent(self):
        messages = []
        session = make_session(result=messages)
        session.state = protocol.STATE_CLOSED

        await session.remote_close()
        self.assertEqual(session.state, protocol.STATE_CLOSED)
        self.assertEqual(messages, [])

    async def test_remote_close_with_exc(self):
        messages = []
        session = make_session(result=messages)

        exc = ValueError()
        await session.remote_close(exc=exc)
        self.assertTrue(session.interrupted)
        self.assertEqual(session.state, protocol.STATE_CLOSING)
        self.assertEqual(messages, [(protocol.SockjsMessage(protocol.MSG_CLOSE, exc), session)])

    async def test_remote_close_exc_in_handler(self):
        handler = make_handler(result=[], exc=True)
        session = make_session(handler=handler)

        await session.remote_close()
        self.assertFalse(session.interrupted)
        self.assertEqual(session.state, protocol.STATE_CLOSING)

    async def test_remote_closed(self):
        messages = []
        session = make_session(result=messages)

        await session.remote_closed()
        self.assertTrue(session.expired)
        self.assertEqual(session.state, protocol.STATE_CLOSED)
        self.assertEqual(messages, [(protocol.ClosedMessage, session)])

    async def test_remote_closed_idempotent(self):
        messages = []
        session = make_session(result=messages)
        session.state = protocol.STATE_CLOSED

        await session.remote_closed()
        self.assertEqual(session.state, protocol.STATE_CLOSED)
        self.assertEqual(messages, [])

    async def test_remote_closed_with_waiter(self):
        messages = []
        session = make_session(result=messages)
        loop = asyncio.get_event_loop()
        session._waiter = waiter = loop.create_future()

        await session.remote_closed()
        self.assertTrue(waiter.done())
        self.assertTrue(session.expired)
        self.assertIsNone(session._waiter)
        self.assertEqual(session.state, protocol.STATE_CLOSED)
        self.assertEqual(messages, [(protocol.ClosedMessage, session)])

    async def test_remote_closed_exc_in_handler(self):
        handler = make_handler(result=[], exc=True)
        session = make_session(handler=handler)

        await session.remote_closed()
        self.assertTrue(session.expired)
        self.assertEqual(session.state, protocol.STATE_CLOSED)

    async def test_remote_message(self):
        messages = []
        session = make_session(result=messages)

        await session.remote_message("msg")
        self.assertEqual(messages, [(protocol.SockjsMessage(protocol.MSG_MESSAGE, "msg"), session)])

    async def test_remote_message_exc(self):
        messages = []
        handler = make_handler(result=messages, exc=True)
        session = make_session(handler=handler)

        await session.remote_message("msg")
        self.assertEqual(messages, [])

    async def test_remote_messages(self):
        messages = []
        session = make_session(result=messages)

        await session.remote_messages(("msg1", "msg2"))
        self.assertEqual(messages, [
            (protocol.SockjsMessage(protocol.MSG_MESSAGE, "msg1"), session),
            (protocol.SockjsMessage(protocol.MSG_MESSAGE, "msg2"), session),
        ])

    async def test_remote_messages_exc(self):
        messages = []
        handler = make_handler(result=messages, exc=True)
        session = make_session(handler=handler)

        await session.remote_messages(("msg1", "msg2"))
        self.assertEqual(messages, [])


class TestSessionManager(TestCase):
    async def test_handler(self):
        handler = make_handler([])
        sm = make_manager(handler=handler)
        session = sm.get("test", True)
        self.assertIs(session.handler, handler)

        await sm.clear()

    async def test_fresh(self):
        sm = make_manager()
        session = make_session()
        sm._add(session)
        self.assertIn("test", sm)

        await sm.clear()

    async def test_add(self):
        sm = make_manager()
        session = make_session()

        sm._add(session)
        self.assertIn("test", sm)
        self.assertIs(sm["test"], session)
        self.assertIs(session.manager, sm)

        await sm.clear()

    async def test_add_expired(self):
        sm = make_manager()
        session = make_session()
        session.expire()

        with self.assertRaises(ValueError):
            sm._add(session)

        await sm.clear()

    async def test_get(self):
        sm = make_manager()
        session = make_session()
        with self.assertRaises(KeyError):
            sm.get("test")

        sm._add(session)
        self.assertIs(sm.get("test"), session)

        await sm.clear()

    async def test_get_unknown_with_default(self):
        sm = make_manager()
        default = object()

        item = sm.get("id", default=default)
        self.assertIs(item, default)

        await sm.clear()

    async def test_get_with_create(self):
        sm = make_manager()

        session = sm.get("test", True)
        self.assertIn(session.id, sm)
        self.assertIsInstance(session, Session)

        await sm.clear()

    async def test_acquire(self):
        sm = make_manager()
        s1 = make_session()
        sm._add(s1)
        s1.acquire = mock.Mock()
        loop = asyncio.get_event_loop()
        s1.acquire.return_value = loop.create_future()
        s1.acquire.return_value.set_result(1)

        scope = make_scope("GET", path="/sockjs/000/000000/test")
        s2 = await sm.acquire(scope, s1)

        self.assertIs(s1, s2)
        self.assertIn(s1.id, sm._acquired_map)
        self.assertTrue(sm._acquired_map[s1.id])
        self.assertTrue(sm.is_acquired(s1))
        self.assertTrue(s1.acquire.called)

        await sm.clear()

    async def test_acquire_unknown(self):
        sm = make_manager()
        session = make_session()
        scope = make_scope("GET", path="/sockjs/000/000000/test")
        with self.assertRaises(KeyError):
            await sm.acquire(scope, session)

        await sm.clear()

    async def test_acquire_locked(self):
        sm = make_manager()
        session = make_session()
        sm._add(session)
        scope = make_scope("GET", path="/sockjs/000/000000/test")
        await sm.acquire(scope, session)

        with self.assertRaises(SessionIsAcquired):
            await sm.acquire(scope, session)

        await sm.clear()

    async def test_release(self):
        sm = make_manager()
        session = sm.get("test", True)
        session.release = mock.Mock()

        scope = make_scope("GET", path="/sockjs/000/000000/test")
        await sm.acquire(scope, session)
        await sm.release(session)

        self.assertNotIn("test", sm._acquired_map)
        self.assertFalse(sm.is_acquired(session))
        self.assertTrue(session.release.called)

        await sm.clear()

    async def test_active_sessions(self):
        sm = make_manager()

        s1 = sm.get("test1", True)
        s2 = sm.get("test2", True)
        s2.expire()

        actives = list(sm.active_sessions())
        self.assertEqual(len(actives), 1)
        self.assertIn(s1, actives)

        await sm.clear()

    async def test_broadcast(self):
        sm = make_manager()

        s1 = sm.get("test1", True)
        s1.state = protocol.STATE_OPEN
        s2 = sm.get("test2", True)
        s2.state = protocol.STATE_OPEN
        sm.broadcast("msg")

        self.assertEqual(list(s1._queue), [(protocol.FRAME_MESSAGE_BLOB, 'a["msg"]')])
        self.assertEqual(list(s2._queue), [(protocol.FRAME_MESSAGE_BLOB, 'a["msg"]')])

        await sm.clear()

    async def test_clear(self):
        sm = make_manager()

        s1 = sm.get("s1", True)
        s1.state = protocol.STATE_OPEN
        s2 = sm.get("s2", True)
        s2.state = protocol.STATE_OPEN

        await sm.clear()

        self.assertFalse(bool(sm))
        self.assertTrue(s1.expired)
        self.assertTrue(s2.expired)
        self.assertEqual(s1.state, protocol.STATE_CLOSED)
        self.assertEqual(s2.state, protocol.STATE_CLOSED)

        await sm.clear()

    async def test_heartbeat(self):
        sm = make_manager()
        self.assertFalse(sm.started)
        self.assertIsNone(sm._gc_future_task)

        sm.start()
        self.assertTrue(sm.started)
        self.assertIsNotNone(sm._gc_timer)

        sm._gc()
        self.assertIsNotNone(sm._gc_future_task)

        gc_future_task = sm._gc_future_task

        sm.stop()
        self.assertFalse(sm.started)
        self.assertIsNone(sm._gc_timer)
        self.assertIsNone(sm._gc_future_task)
        self.assertTrue(gc_future_task._must_cancel)

        await sm.clear()

    async def test_heartbeat_task(self):
        sm = make_manager()
        sm._gc_future_task = mock.Mock()

        await sm._gc_task()
        self.assertTrue(sm.started)
        self.assertIsNone(sm._gc_future_task)

        await sm.clear()

    async def test_gc_expire(self):
        sm = make_manager()
        session = make_session()

        sm._add(session)
        scope = make_scope("GET", path="/sockjs/000/000000/test")
        await sm.acquire(scope, session)
        await sm.release(session)

        session.expires = datetime.now() - timedelta(seconds=30)

        await sm._gc_task()
        self.assertNotIn(session.id, sm)
        self.assertTrue(session.expired)
        self.assertEqual(session.state, protocol.STATE_CLOSED)

        await sm.clear()

    async def test_gc_expire_acquired(self):
        sm = make_manager()
        session = make_session()
        sm._add(session)
        scope = make_scope("GET", path="/sockjs/000/000000/test")
        await sm.acquire(scope, session)
        session.expires = datetime.now() - timedelta(seconds=30)
        await sm._gc_task()

        self.assertNotIn(session.id, sm)
        self.assertNotIn(session.id, sm._acquired_map)
        self.assertTrue(session.expired)
        self.assertEqual(session.state, protocol.STATE_CLOSED)

        await sm.clear()

    async def test_gc_one_expire(self):
        sm = make_manager()
        s1 = make_session("id1")
        s2 = make_session("id2")

        sm._add(s1)
        sm._add(s2)
        scope = make_scope("GET", path="/sockjs/000/000000/test")
        await sm.acquire(scope, s1)
        await sm.acquire(scope, s2)
        await sm.release(s1)
        await sm.release(s2)

        s1.expires = datetime.now() - timedelta(seconds=30)

        await sm._gc_task()
        self.assertNotIn(s1.id, sm)
        self.assertIn(s2.id, sm)

        await sm.clear()

    async def test_emits_warning_on_del(self):
        sm = make_manager()
        s1 = make_session("id1")
        s2 = make_session("id2")

        sm._add(s1)
        sm._add(s2)

        with self.assertWarns(RuntimeWarning) as warning:
            getattr(sm, "__del__")()
            msg = (
                "Unclosed _sessions! Please call "
                "`await SessionManager.clear()` before del"
            )
            self.assertEqual(warning.warnings[0].message.args[0], msg)

        await sm.clear()

    async def test_does_not_emits_warning_on_del_if_no_sessions(self):
        sm = make_manager()
        s1 = make_session("id1")
        s2 = make_session("id2")

        sm._add(s1)
        sm._add(s2)

        await sm.clear()
        getattr(sm, "__del__")()
