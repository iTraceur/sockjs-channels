import asyncio

from channels.testing import WebsocketCommunicator
from django.test import TestCase

from sockjs import protocol
from sockjs.transports import websocket
from .utils import (
    make_application,
    make_future,
    make_manager,
    make_mocked_coroutine,
    make_websocket_scope,
)

path = "/sockjs/000/000000/websocket"


def make_transport(scope=None):
    if not scope:
        scope = make_websocket_scope(path)
    manager = make_manager()
    session = manager.get("TestSessionWebsocket", create=True, scope=scope)

    transport = websocket.WebsocketConsumer(manager=manager, session=session, create=True)
    transport.scope = scope
    return transport


class TestSessionWebsocket(TestCase):
    async def test_handle_session_interrupted(self):
        transport = make_transport()
        transport.session.interrupted = True
        send = transport.send = make_mocked_coroutine(None)

        self.assertTrue(transport.session.interrupted)
        await transport.handle_session()
        send.assert_called_with('c[1002,"Connection interrupted"]')

        await transport.manager.clear()

    async def test_handle_session_closing(self):
        transport = make_transport()
        send = transport.send = make_mocked_coroutine(None)
        transport.session.interrupted = False
        transport.session.state = protocol.STATE_CLOSING
        transport.session.remote_closed = make_future(1)
        await transport.handle_session()
        transport.session.remote_closed.assert_called_with()
        send.assert_called_with('c[3000,"Go away!"]')

        await transport.manager.clear()

    async def test_handle_session_closed(self):
        transport = make_transport()
        send = transport.send = make_mocked_coroutine(None)
        transport.session.interrupted = False
        transport.session.state = protocol.STATE_CLOSED
        transport.session.remote_closed = make_future(1)
        await transport.handle_session()
        transport.session.remote_closed.assert_called_with()
        send.assert_called_with('c[3000,"Go away!"]')

        await transport.manager.clear()

    async def test_process_acquire_send_and_remote_closed(self):
        transport = make_transport()
        transport.session.interrupted = False
        transport.session.remote_closed = make_mocked_coroutine()
        transport.manager.acquire = make_mocked_coroutine()
        communicator = WebsocketCommunicator(transport, path)
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

        await transport.send("test msg")
        response = await communicator.receive_from()
        self.assertEqual(response, "test msg")

        await transport.manager.clear()
        transport.session.remote_closed.assert_called_once_with()
        self.assertTrue(transport.manager.acquire.called)

    async def test_server_close(self):
        reached_closed = False

        loop = asyncio.get_event_loop()

        async def handler(msg, session):
            nonlocal reached_closed
            if msg.type == protocol.MSG_OPEN:
                asyncio.ensure_future(session.remote_message("TEST MSG"))
            elif msg.type == protocol.MSG_MESSAGE:
                # To reproduce the ordering which makes the issue
                loop.call_later(0.05, session.close)

                if msg.data == 'close':
                    session.close()
            elif msg.type == protocol.MSG_CLOSED:
                reached_closed = True

        communicator = WebsocketCommunicator(make_application(handler=handler), path)
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

        response = await communicator.receive_from()
        self.assertEqual(response, "o")

        response = await communicator.receive_from()
        self.assertEqual(response, 'c[3000,"Go away!"]')

        self.assertTrue(reached_closed)

    async def test_websocket(self):
        reached_closed = False
        async def handler(msg, session):
            nonlocal reached_closed
            if msg.type == protocol.MSG_OPEN:
                session.send("open")
            elif msg.type == protocol.MSG_MESSAGE:
                if msg.data == 'close':
                    session.close()
                else:
                    session.send(msg.data + " world")
            elif msg.type == protocol.MSG_CLOSED:
                reached_closed = True

        communicator = WebsocketCommunicator(make_application(handler=handler), path)
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

        response = await communicator.receive_from()
        self.assertEqual(response, "o")

        response = await communicator.receive_from()
        self.assertEqual(response, 'a["open"]')

        await communicator.send_to("[\"hello\"]")
        response = await communicator.receive_from()
        self.assertEqual(response, 'a["hello world"]')

        await communicator.send_to("\"close\"")
        response = await communicator.receive_from()
        self.assertEqual(response, 'c[3000,"Go away!"]')

        self.assertTrue(reached_closed)

    async def test_bad_json(self):
        transport = make_transport()
        transport.session.remote_closed = make_future(1)
        communicator = WebsocketCommunicator(transport, path)
        communicator.scope = transport.scope
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

        response = await communicator.receive_from()
        self.assertEqual(response, "o")

        await communicator.send_to("{]")
        with self.assertRaises(AssertionError):
            await communicator.receive_from()
        transport.session.remote_closed.assert_called_with()

        await transport.manager.clear()

    async def test_acquire_fail(self):
        transport = make_transport()
        communicator = WebsocketCommunicator(transport, path)
        communicator.scope = transport.scope

        transport.session.id = "ErrorID"

        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

        response = await communicator.receive_from()
        self.assertEqual(response, 'c[3000,"Go away!"]')

        await transport.manager.clear()

    async def test_connection_still_open(self):
        transport = make_transport()
        communicator = WebsocketCommunicator(transport, path)
        communicator.scope = transport.scope
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

        response = await communicator.receive_from()
        self.assertEqual(response, "o")

        await transport.handle_session()

        response = await communicator.receive_from()
        self.assertEqual(response, 'c[2010,"Another connection still open"]')

        await transport.manager.clear()

    async def test_disconnect(self):
        transport = make_transport()
        communicator = WebsocketCommunicator(transport, path)
        communicator.scope = transport.scope
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

        response = await communicator.receive_from()
        self.assertEqual(response, "o")

        await communicator.disconnect()

        self.assertFalse(transport.manager.is_acquired(transport.session))
        self.assertIsNone(transport.session_loop_task)

        await transport.manager.clear()

    async def test_session_has_scope(self):
        transport = make_transport()
        communicator = WebsocketCommunicator(transport, path)
        communicator.scope = transport.scope
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

        response = await communicator.receive_from()
        self.assertEqual(response, "o")

        self.assertEqual(transport.scope, communicator.scope)
        self.assertEqual(transport.session.scope, communicator.scope)

        await transport.manager.clear()
