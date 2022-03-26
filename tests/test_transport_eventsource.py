from channels.testing import HttpCommunicator
from django.test import TestCase

from sockjs.transports import eventsource
from .utils import make_scope, make_manager, make_mocked_coroutine, make_future

path = "/sockjs/000/000000/eventsource"


def make_transport():
    scope = make_scope("GET", path=path)
    manager = make_manager()
    session = manager.get("TestSessionEventSource", create=True, scope=scope)

    transport = eventsource.EventsourceConsumer(manager=manager, session=session)
    transport.scope = scope
    return transport


class TestSessionEventSource(TestCase):
    async def test_streaming_send(self):
        transport = make_transport()

        send = transport.send_body = make_mocked_coroutine(None)
        stop = await transport.send_message("text data", more_body=True)
        send.assert_called_with(b"data: text data\r\n\r\n", more_body=True)
        self.assertFalse(stop)
        self.assertEqual(transport.size, len(b"data: text data\r\n\r\n"))

        transport.maxsize = 1
        stop = await transport.send_message("text data", more_body=True)
        self.assertTrue(stop)

        await transport.manager.clear()

    async def test_process(self):
        transport = make_transport()
        transport.maxsize = 1
        communicator = HttpCommunicator(transport, "GET", path)
        communicator.scope = transport.scope
        response = await communicator.get_response()

        self.assertEqual(response['status'], 200)

        await transport.manager.clear()

    async def test_session_has_scope(self):
        transport = make_transport()
        transport.session.release = make_future(1)
        transport.maxsize = 1
        communicator = HttpCommunicator(transport, "GET", path)
        communicator.scope = transport.scope
        await communicator.get_response()

        self.assertEqual(transport.scope, communicator.scope)
        self.assertTrue(transport.session.release.called)
        self.assertEqual(transport.session.scope, communicator.scope)

        await transport.manager.clear()
