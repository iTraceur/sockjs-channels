from channels.testing import WebsocketCommunicator
from django.test import TestCase

from sockjs import protocol
from sockjs.protocol import STATE_CLOSED, STATE_OPEN, message_frame
from sockjs.transports import rawwebsocket
from .utils import make_websocket_scope, make_manager, make_future

path = "/sockjs/websocket"


def make_transport(scope=None, handler=None):
    if not scope:
        scope = make_websocket_scope(path)
    manager = make_manager(handler)
    session = manager.get("TestSessionWebsocket", create=True, scope=scope)

    transport = rawwebsocket.RawWebsocketConsumer(manager=manager, session=session, create=True)
    transport.scope = scope
    return transport


class TestSessionWebsocket(TestCase):
    async def test_raw_websocket_send(self):
        transport = make_transport()
        communicator = WebsocketCommunicator(transport, path)
        communicator.scope = transport.scope
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

        await transport.send("test msg")
        response = await communicator.receive_from()
        self.assertEqual(response, "test msg")

        await transport.manager.clear()

    async def test_send_bytes(self):
        async def handler(msg, session):
            if msg.type == protocol.MSG_MESSAGE:
                session.send(msg.data)

        transport = make_transport(handler=handler)
        communicator = WebsocketCommunicator(transport, path)
        communicator.scope = transport.scope
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

        transport.session.send("test msg1")
        response = await communicator.receive_from()
        self.assertEqual(response, "test msg1")

        await communicator.send_to(bytes_data=b"message")
        response = await communicator.receive_from()
        self.assertEqual(response, "message")

        await transport.manager.clear()

    async def test_session_send(self):
        transport = make_transport()
        communicator = WebsocketCommunicator(transport, path)
        communicator.scope = transport.scope
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

        transport.session.send("test msg1")
        transport.session.send("test msg2")
        response = await communicator.receive_from()
        self.assertEqual(response, "test msg1")
        response = await communicator.receive_from()
        self.assertEqual(response, "test msg2")

        await transport.manager.clear()

    async def test_send_frame(self):
        transport = make_transport()
        communicator = WebsocketCommunicator(transport, path)
        communicator.scope = transport.scope
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

        transport.session.send_frame(message_frame("test msg1"))
        transport.session.send_frame(message_frame("test msg2"))

        response = await communicator.receive_from()
        self.assertEqual(response, "test msg1")
        response = await communicator.receive_from()
        self.assertEqual(response, "test msg2")

        await transport.manager.clear()

    async def test_send_close(self):
        transport = make_transport()
        transport.session.remote_closed = make_future(1)
        communicator = WebsocketCommunicator(transport, path)
        communicator.scope = transport.scope
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

        transport.session.close()

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

        with self.assertRaises(AssertionError):
            await communicator.receive_from()

        await transport.manager.clear()

    async def test_disconnect(self):
        transport = make_transport()
        communicator = WebsocketCommunicator(transport, path)
        communicator.scope = transport.scope
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

        self.assertEqual(transport.session.state, STATE_OPEN)
        await communicator.disconnect()
        self.assertEqual(transport.session.state, STATE_CLOSED)

        await transport.manager.clear()
