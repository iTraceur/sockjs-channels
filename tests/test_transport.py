from channels.testing import HttpCommunicator, WebsocketCommunicator
from django.test import TestCase

from sockjs import protocol
from sockjs.transports import base
from .utils import make_manager, make_mocked_coroutine, make_future, make_scope, make_websocket_scope


def make_http_transport(scope=None):
    if not scope:
        scope = make_scope("GET", path="/sockjs/000/000000/test")
    manager = make_manager()
    session = manager.get("TestHttpStreaming", create=True, scope=scope)

    transport = base.HttpStreamingConsumer(manager=manager, session=session)
    transport.scope = scope
    return transport


def make_websocket_transport(scope):
    manager = make_manager()
    session = manager.get("TestWebsocketStreaming", create=True, scope=scope)

    transport = base.BaseWebsocketConsumer(manager=manager, session=session)
    transport.scope = scope
    return transport


class TestTransport(TestCase):
    async def test_http_transport_ctor(self):
        manager = object()
        session = object()

        transport = base.HttpStreamingConsumer(manager=manager, session=session)
        self.assertIs(transport.manager, manager)
        self.assertIs(transport.session, session)

    async def test_websocket_transport_ctor(self):
        manager = object()
        session = object()

        transport = base.BaseWebsocketConsumer(manager=manager, session=session)
        self.assertIs(transport.manager, manager)
        self.assertIs(transport.session, session)

    async def test_streaming_send(self):
        transport = make_http_transport()

        send = transport.send_body = make_mocked_coroutine(None)
        stop = await transport.send_message("text data", more_body=True)
        self.assertFalse(stop)
        self.assertEqual(transport.size, len(b"text data\n"))
        send.assert_called_with(b"text data\n", more_body=True)

        transport.maxsize = 1
        stop = await transport.send_message("text data", more_body=True)
        self.assertTrue(stop)

        await transport.manager.clear()

    async def test_handle_session_interrupted(self):
        transport = make_http_transport()
        transport.session.interrupted = True
        send = transport.send_body = make_mocked_coroutine(None)

        self.assertTrue(transport.session.interrupted)
        await transport.handle_session()
        send.assert_called_with(b'c[1002,"Connection interrupted"]\n', more_body=False)

        await transport.manager.clear()

    async def test_handle_session_closing(self):
        transport = make_http_transport()
        send = transport.send_body = make_mocked_coroutine(None)
        transport.session.interrupted = False
        transport.session.state = protocol.STATE_CLOSING
        transport.session.remote_closed = make_future(1)
        await transport.handle_session()
        transport.session.remote_closed.assert_called_with()
        send.assert_called_with(b'c[3000,"Go away!"]\n', more_body=False)

        await transport.manager.clear()

    async def test_handle_session_closed(self):
        transport = make_http_transport()
        send = transport.send_body = make_mocked_coroutine(None)
        transport.session.interrupted = False
        transport.session.state = protocol.STATE_CLOSED
        transport.session.remote_closed = make_future(1)
        await transport.handle_session()
        transport.session.remote_closed.assert_called_with()
        send.assert_called_with(b'c[3000,"Go away!"]\n', more_body=False)

        await transport.manager.clear()

    async def test_connection_still_open(self):
        transport = make_http_transport()
        send = transport.send_body = make_mocked_coroutine(None)
        transport.session.interrupted = False
        transport.session.state = protocol.STATE_NEW
        await transport.manager.acquire(transport.scope, transport.session)
        await transport.handle_session()
        send.assert_called_with(b'c[2010,"Another connection still open"]\n', more_body=False)

        await transport.manager.clear()

    async def test_http_session_has_scope(self):
        path = "/sockjs/000/000000/test"
        scope = make_scope("POST", path)
        transport = make_http_transport(scope)
        body = b"[message]"
        communicator = HttpCommunicator(transport, "POST", path, body=body)
        communicator.scope = scope
        await communicator.get_response()
        self.assertEqual(transport.scope, communicator.scope)
        self.assertEqual(transport.session.scope, communicator.scope)
        self.assertEqual(transport.body, [body])

        await transport.manager.clear()

    async def test_websocket_session_has_scope(self):
        path = "/sockjs/000/000000/websocket"
        scope = make_websocket_scope(path)
        transport = make_websocket_transport(scope)
        communicator = WebsocketCommunicator(transport, path)
        communicator.scope = scope
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)
        self.assertEqual(transport.scope, communicator.scope)
        self.assertEqual(transport.session.scope, communicator.scope)

        await transport.manager.clear()
