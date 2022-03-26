from channels.testing import HttpCommunicator
from django.test import TestCase

from sockjs.transports import xhr
from .utils import make_scope, make_manager, make_future

path = "/sockjs/000/000000/xhr"


def make_transport(scope=None):
    if not scope:
        scope = make_scope("POST", path=path)
    manager = make_manager()
    session = manager.get("TestSessionXhr", create=True, scope=scope)

    transport = xhr.XHRConsumer(manager=manager, session=session)
    transport.scope = scope
    return transport


class TestSessionXhr(TestCase):
    async def test_process(self):
        transport = make_transport()
        communicator = HttpCommunicator(transport, "POST", path)
        communicator.scope = transport.scope
        response = await communicator.get_response()

        self.assertEqual(response['status'], 200)
        self.assertEqual(response['body'], b'o\n')

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
        transport.session.release = make_future(1)
        communicator = HttpCommunicator(transport, "POST", path)
        communicator.scope = transport.scope
        await communicator.get_response()

        self.assertEqual(transport.scope, communicator.scope)
        self.assertTrue(transport.session.release.called)
        self.assertEqual(transport.session.scope, communicator.scope)

        await transport.manager.clear()
