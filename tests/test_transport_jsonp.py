from channels.testing import HttpCommunicator
from django.test import TestCase

from sockjs.transports import jsonp
from .utils import make_scope, make_manager, make_mocked_coroutine, make_future


def make_transport(method, path):
    scope = make_scope(method, path=path)
    manager = make_manager()
    session = manager.get("TestSessionJsonP", create=True, scope=scope)

    transport = jsonp.JSONPollingConsumer(manager=manager, session=session)
    transport.scope = scope
    return transport


class TestSessionXhr(TestCase):
    async def test_streaming_send(self):
        transport = make_transport("GET", path="/sockjs/000/000000/jsonp?c=cb")
        transport.callback = 'cb'

        send = transport.send_body = make_mocked_coroutine(None)
        await transport.send_message("text data", more_body=True)
        send.assert_called_with(b'/**/cb("text data");\r\n', more_body=False)

        await transport.manager.clear()

    async def test_process(self):
        path = "/sockjs/000/000000/jsonp?c=cb"
        transport = make_transport("GET", path=path)
        communicator = HttpCommunicator(transport, "GET", path)
        communicator.scope = transport.scope
        response = await communicator.get_response()

        self.assertEqual(response['status'], 200)

        await transport.manager.clear()

    async def test_process_no_callback(self):
        path = "/sockjs/000/000000/jsonp"
        transport = make_transport("GET", path)
        transport.session.remote_closed = make_future(1)
        communicator = HttpCommunicator(transport, "GET", path)
        communicator.scope = transport.scope
        response = await communicator.get_response()

        assert transport.session.remote_closed.called
        self.assertEqual(response['status'], 500)

        await transport.manager.clear()

    async def test_process_bad_callback(self):
        path = "/sockjs/000/000000/jsonp?c=callback!!!!"
        transport = make_transport("GET", path)
        transport.session.remote_closed = make_future(1)
        communicator = HttpCommunicator(transport, "GET", path)
        communicator.scope = transport.scope
        response = await communicator.get_response()

        assert transport.session.remote_closed.called
        self.assertEqual(response['status'], 500)

        await transport.manager.clear()

    async def test_process_not_supported(self):
        path = "/sockjs/000/000000/jsonp?c=cb"
        transport = make_transport("PUT", path=path)
        communicator = HttpCommunicator(transport, "PUT", path)
        communicator.scope = transport.scope
        response = await communicator.get_response()

        self.assertEqual(response['status'], 400)

        await transport.manager.clear()

    async def test_process_bad_encoding(self):
        path = "/sockjs/000/000000/jsonp?c=callback"
        transport = make_transport("POST", path)
        hearders = [(b"content-type", b"application/x-www-form-urlencoded")]
        communicator = HttpCommunicator(transport, "POST", path, body=b"test", headers=hearders)
        communicator.scope = transport.scope
        response = await communicator.get_response()

        self.assertEqual(response['status'], 500)

        await transport.manager.clear()

    async def test_process_no_payload(self):
        path = "/sockjs/000/000000/jsonp?c=callback"
        transport = make_transport("POST", path)
        headers = [(b"content-type", b"application/x-www-form-urlencoded")]
        communicator = HttpCommunicator(transport, "POST", path, body=b"d=", headers=headers)
        communicator.scope = transport.scope
        response = await communicator.get_response()

        self.assertEqual(response['status'], 500)

        await transport.manager.clear()

    async def test_process_bad_json(self):
        path = "/sockjs/000/000000/jsonp?c=callback"
        transport = make_transport("POST", path)
        communicator = HttpCommunicator(transport, "POST", path, body=b"{]")
        communicator.scope = transport.scope
        response = await communicator.get_response()

        self.assertEqual(response['status'], 500)

        await transport.manager.clear()

    async def test_process_message(self):
        path = "/sockjs/000/000000/jsonp?c=callback"
        transport = make_transport("POST", path)
        transport.session.remote_messages = make_future(1)
        communicator = HttpCommunicator(transport, "POST", path, body=b'["msg1","msg2"]')
        communicator.scope = transport.scope
        response = await communicator.get_response()

        self.assertEqual(response['status'], 200)
        transport.session.remote_messages.assert_called_with(["msg1", "msg2"])

        await transport.manager.clear()

    async def test_session_has_scope(self):
        path = "/sockjs/000/000000/jsonp?c=callback"
        transport = make_transport("GET", path)
        transport.session.release = make_future(1)
        communicator = HttpCommunicator(transport, "GET", path)
        communicator.scope = transport.scope
        await communicator.get_response()

        self.assertEqual(transport.scope, communicator.scope)
        self.assertTrue(transport.session.release.called)
        self.assertEqual(transport.session.scope, communicator.scope)

        await transport.manager.clear()
