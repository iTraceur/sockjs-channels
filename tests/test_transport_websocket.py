import asyncio

from channels.testing import WebsocketCommunicator
from django.test import TestCase

from sockjs import MSG_OPEN, MSG_CLOSED, MSG_MESSAGE
from sockjs.transports import websocket
from .utils import make_manager, make_websocket_scope, make_mocked_coroutine, make_application

path = "/sockjs/000/000000/websocket"


def make_transport(scope=None):
    if not scope:
        scope = make_websocket_scope(path)
    manager = make_manager()
    session = manager.get("TestSessionWebsocket", create=True, scope=scope)

    transport = websocket.WebsocketConsumer(manager=manager, session=session)
    transport.scope = scope
    return transport


class TestSessionWebsocket(TestCase):
    async def test_process_acquire_send_and_remote_closed(self):
        transport = make_transport()
        transport.session.interrupted = False
        transport.session.remote_closed = make_mocked_coroutine()
        transport.manager.acquire = make_mocked_coroutine()
        communicator = WebsocketCommunicator(transport, path)
        communicator.scope = transport.scope
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
            if msg.type == MSG_OPEN:
                asyncio.ensure_future(session.remote_message("TEST MSG"))
            elif msg.type == MSG_MESSAGE:
                # To reproduce the ordering which makes the issue
                loop.call_later(0.05, session.close)

                if msg.data == 'close':
                    session.close()
            elif msg.type == MSG_CLOSED:
                reached_closed = True

        communicator = WebsocketCommunicator(make_application(handler=handler), path)
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

        response = await communicator.receive_from()
        self.assertEqual(response, "o")

        response = await communicator.receive_from()
        self.assertEqual(response, 'c[3000,"Go away!"]')

        self.assertTrue(reached_closed)

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
