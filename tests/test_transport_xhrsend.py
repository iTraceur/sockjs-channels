from channels.testing import HttpCommunicator
from django.test import TestCase

from sockjs.transports import xhrsend
from .utils import make_scope, make_manager, make_future

path = "/sockjs/000/000000/xhr_send"


def make_transport(scope=None):
    if not scope:
        scope = make_scope("POST", path=path)
    manager = make_manager()
    session = manager.get("TestSessionXhrSend", create=True, scope=scope)

    transport = xhrsend.XHRSendConsumer(manager=manager, session=session)
    transport.scope = scope
    return transport


class TestSessionXhr(TestCase):
    async def test_not_supported_method(self):
        scope = make_scope("PUT", path)
        transport = make_transport(scope)
        communicator = HttpCommunicator(transport, "PUT", path)
        communicator.scope = scope
        response = await communicator.get_response()

        self.assertEqual(response['status'], 403)

        await transport.manager.clear()

    async def test_no_payload(self):
        transport = make_transport()
        communicator = HttpCommunicator(transport, "POST", path)
        communicator.scope = transport.scope
        response = await communicator.get_response()

        self.assertEqual(response['status'], 500)

        await transport.manager.clear()

    async def test_bad_json(self):
        transport = make_transport()
        communicator = HttpCommunicator(transport, "POST", path, body=b"{]")
        communicator.scope = transport.scope
        response = await communicator.get_response()

        self.assertEqual(response['status'], 500)

        await transport.manager.clear()

    async def test_post_message(self):
        transport = make_transport()
        transport.session.remote_messages = make_future(1)
        communicator = HttpCommunicator(transport, "POST", path, body=b'["msg1","msg2"]')
        communicator.scope = transport.scope
        response = await communicator.get_response()

        self.assertEqual(response['status'], 204)
        transport.session.remote_messages.assert_called_with(["msg1", "msg2"])

        await transport.manager.clear()

    async def test_OPTIONS(self):
        scope = make_scope("OPTIONS", path)
        transport = make_transport(scope)
        communicator = HttpCommunicator(transport, "OPTIONS", path)
        communicator.scope = scope
        response = await communicator.get_response()

        self.assertEqual(response['status'], 204)

        await transport.manager.clear()

    async def test_session_has_scope(self):
        transport = make_transport()
        communicator = HttpCommunicator(transport, "POST", path)
        communicator.scope = transport.scope
        await communicator.get_response()

        self.assertEqual(transport.scope, communicator.scope)
        self.assertEqual(transport.session.scope, communicator.scope)

        await transport.manager.clear()
