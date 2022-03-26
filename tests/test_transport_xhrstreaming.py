from channels.testing import HttpCommunicator
from django.test import TestCase

from sockjs.transports import xhrstreaming
from .utils import make_scope, make_manager, make_future

path = "/sockjs/000/000000/xhr_streaming"


def make_transport(scope=None):
    if not scope:
        scope = make_scope("POST", path)
    manager = make_manager()
    session = manager.get("TestXHRStreaming", create=True, scope=scope)

    transport = xhrstreaming.XHRStreamingConsumer(manager=manager, session=session)
    transport.scope = scope
    return transport


class TestXHRStreaming(TestCase):
    async def test_process(self):
        scope = make_scope("POST", path)
        transport = make_transport(scope)
        transport.maxsize = 2048
        handle = transport.handle_session = make_future(1)
        communicator = HttpCommunicator(transport, "POST", path)
        communicator.scope = scope
        response = await communicator.get_response()

        self.assertTrue(handle.called)
        self.assertEqual(response['status'], 200)
        self.assertEqual(response['body'], b'h' * 2048 + b'\n')

        await transport.manager.clear()

    async def test_process_OPTIONS(self):
        scope = make_scope("OPTIONS", path)
        transport = make_transport(scope)
        communicator = HttpCommunicator(transport, "OPTIONS", path)
        communicator.scope = scope
        response = await communicator.get_response()

        self.assertEqual(response['status'], 204)

        await transport.manager.clear()

    async def test_session_has_scope(self):
        transport = make_transport()
        transport.maxsize = 2048
        transport.handle_session = make_future(1)
        communicator = HttpCommunicator(transport, "POST", path)
        communicator.scope = transport.scope
        await communicator.get_response()

        self.assertEqual(transport.scope, communicator.scope)
        self.assertEqual(transport.session.scope, communicator.scope)

        await transport.manager.clear()
