from channels.testing import WebsocketCommunicator
from django.test import TestCase

from sockjs.protocol import STATE_CLOSED, STATE_OPEN
from sockjs.transports import rawwebsocket
from .utils import make_websocket_scope, make_manager

path = "/sockjs/websocket"


def make_transport(scope=None):
    if not scope:
        scope = make_websocket_scope(path)
    manager = make_manager()
    session = manager.get("TestSessionWebsocket", create=True, scope=scope)

    transport = rawwebsocket.RawWebsocketConsumer(manager=manager, session=session)
    transport.scope = scope
    return transport


class TestSessionWebsocket(TestCase):
    async def test_raw_websocket(self):
        transport = make_transport()
        communicator = WebsocketCommunicator(transport, path)
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

        await transport.send("test msg")
        response = await communicator.receive_from()
        self.assertEqual(response, "test msg")

        self.assertEqual(transport.session.state, STATE_OPEN)
        await communicator.disconnect()
        self.assertEqual(transport.session.state, STATE_CLOSED)

        await transport.manager.clear()
