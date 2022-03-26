from channels.testing import HttpCommunicator
from django.test import TestCase

from sockjs.transports import htmlfile
from .utils import make_scope, make_manager, make_mocked_coroutine, make_future


def make_transport(path):
    scope = make_scope("GET", path=path)
    manager = make_manager()
    session = manager.get("TestSessionHtmlFile", create=True, scope=scope)

    transport = htmlfile.HTMLFileConsumer(manager=manager, session=session)
    transport.scope = scope
    return transport


class TestSessionXhr(TestCase):
    async def test_streaming_send(self):
        transport = make_transport(path="/sockjs/000/000000/htmlfile?c=callback")

        send = transport.send_body = make_mocked_coroutine(None)
        stop = await transport.send_message("text data", more_body=True)
        send.assert_called_with(b'<script>\np("text data");\n</script>\r\n', more_body=True)
        self.assertFalse(stop)
        self.assertEqual(transport.size, len(b'<script>\np("text data");\n</script>\r\n'))

        transport.maxsize = 1
        stop = await transport.send_message("text data", more_body=True)
        self.assertTrue(stop)

        await transport.manager.clear()

    async def test_process(self):
        path = "/sockjs/000/000000/htmlfile?c=callback"
        transport = make_transport(path)
        transport.maxsize = 1
        communicator = HttpCommunicator(transport, "GET", path)
        communicator.scope = transport.scope
        response = await communicator.get_response()

        self.assertEqual(response['status'], 200)

        await transport.manager.clear()

    async def test_process_no_callback(self):
        path = "/sockjs/000/000000/htmlfile"
        transport = make_transport(path)
        transport.session.remote_closed = make_future(1)
        communicator = HttpCommunicator(transport, "GET", path)
        communicator.scope = transport.scope
        response = await communicator.get_response()

        assert transport.session.remote_closed.called
        self.assertEqual(response['status'], 500)

        await transport.manager.clear()

    async def test_process_bad_callback(self):
        path = "/sockjs/000/000000/htmlfile?c=callback!!!!"
        transport = make_transport(path)
        transport.session.remote_closed = make_future(1)
        communicator = HttpCommunicator(transport, "GET", path)
        communicator.scope = transport.scope
        response = await communicator.get_response()

        assert transport.session.remote_closed.called
        self.assertEqual(response['status'], 500)

        await transport.manager.clear()

    async def test_session_has_scope(self):
        path = "/sockjs/000/000000/htmlfile?c=callback"
        transport = make_transport(path)
        transport.session.release = make_future(1)
        transport.maxsize = 1
        communicator = HttpCommunicator(transport, "GET", path)
        communicator.scope = transport.scope
        await communicator.get_response()

        self.assertEqual(transport.scope, communicator.scope)
        self.assertTrue(transport.session.release.called)
        self.assertEqual(transport.session.scope, communicator.scope)

        await transport.manager.clear()
