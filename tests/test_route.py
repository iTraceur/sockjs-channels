from channels.testing import HttpCommunicator, WebsocketCommunicator
from django.test import TestCase

import sockjs
from sockjs.transports.base import HttpStreamingConsumer
from .utils import make_application


class RouteTests(TestCase):
    async def test_greeting(self):
        communicator = HttpCommunicator(make_application(), "GET", "/sockjs")
        response = await communicator.get_response()

        self.assertEqual(response["body"], b'Welcome to SockJS!\n')

    async def test_info(self):
        communicator = HttpCommunicator(make_application(), "GET", "/sockjs/info")
        response = await communicator.get_response()

        info = sockjs.protocol.loads(response["body"].decode())

        self.assertIn("websocket", info)
        self.assertIn("cookie_needed", info)

    async def test_info_entropy(self):
        communicator = HttpCommunicator(make_application(), "GET", "/sockjs/info")
        response = await communicator.get_response()
        entropy1 = sockjs.protocol.loads(response["body"].decode())["entropy"]

        communicator = HttpCommunicator(make_application(), "GET", "/sockjs/info")
        response = await communicator.get_response()
        entropy2 = sockjs.protocol.loads(response["body"].decode())["entropy"]

        self.assertNotEqual(entropy1, entropy2)

    async def test_info_options(self):
        communicator = HttpCommunicator(make_application(), "OPTIONS", "/sockjs/info")
        response = await communicator.get_response()

        self.assertEqual(response["status"], 200)

        headers = dict(response["headers"])
        self.assertIn(b"Cache-Control", headers)
        self.assertIn(b"Content-Type", headers)
        self.assertIn(b"Content-Length", headers)
        self.assertIn(b"Set-Cookie", headers)
        self.assertIn(b"Access-Control-Allow-Origin", headers)

    async def test_iframe(self):
        communicator = HttpCommunicator(make_application(), "GET", "/sockjs/iframe.html")
        response = await communicator.get_response()
        sockjs_cdn = "https://cdn.jsdelivr.net/npm/sockjs-client@1/dist/sockjs.js"
        text = """<!DOCTYPE html>
<html>
<head>
<meta http-equiv="X-UA-Compatible" content="IE=edge" />
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <script src="%s"></script>
  <script>
    document.domain = document.domain;
    SockJS.bootstrap_iframe();
  </script>
</head>
<body>
  <h2>Don"t panic!</h2>
  <p>This is a SockJS hidden iframe. It"s used for cross domain magic.</p>
</body>
</html>""" % sockjs_cdn

        self.assertEqual(response["body"].decode(), text)
        self.assertIn(b"ETag", dict(response["headers"]))

    async def test_iframe_cache(self):
        communicator = HttpCommunicator(make_application(), "GET", "/sockjs/iframe.html",
                                        headers=[(b"IF-NONE-MATCH", b"test")])
        response = await communicator.get_response()

        self.assertEqual(response["status"], 304)

    async def test_handler_unknown_transport(self):
        communicator = HttpCommunicator(make_application(), "GET", "/sockjs/000/00000000/unknown")
        response = await communicator.get_response()

        self.assertEqual(response['status'], 404)

    async def test_handler_emptry_session(self):
        communicator = HttpCommunicator(make_application(), "GET", "/sockjs/000//xhr")
        response = await communicator.get_response()

        self.assertEqual(response['status'], 404)

    async def test_handler_bad_session_id(self):
        communicator = HttpCommunicator(make_application(), "GET", "/sockjs/000/test.1/xhr")
        response = await communicator.get_response()

        self.assertEqual(response['status'], 404)

    async def test_handler_bad_server_id(self):
        communicator = HttpCommunicator(make_application(), "GET", "/sockjs/test.1/00000000/xhr")
        response = await communicator.get_response()

        self.assertEqual(response['status'], 404)

    async def test_new_session_before_read(self):
        communicator = HttpCommunicator(make_application(), "GET", "/sockjs/000/00000000/xhr_send")
        response = await communicator.get_response()

        self.assertEqual(response['status'], 404)

    async def test_transport(self):
        params = []

        class Consumer(HttpStreamingConsumer):
            async def handle(self, body):
                params.append((self.manager, self.session, self.scope["path"]))
                await self.send_response(200, b'')

        app = make_application(name="test", consumers={"xhr": (True, Consumer)})
        communicator = HttpCommunicator(app, "GET", "/sockjs/000/s1/xhr")
        response = await communicator.get_response()

        self.assertEqual(response["status"], 200)
        manager = sockjs.get_manager(app.routing, name='test')
        self.assertEqual(params[0], (manager, manager["s1"], communicator.scope["path"]))

    async def test_fail_transport(self):
        class Consumer(HttpStreamingConsumer):
            async def handle(self, body):
                raise Exception("Error")

        app = make_application(name="test", consumers={"test": (True, Consumer)})
        communicator = HttpCommunicator(app, "GET", "/sockjs/000/session/test")
        response = await communicator.get_response()

        self.assertEqual(response["status"], 500)

    async def test_release_session_for_failed_transport(self):
        class Consumer(HttpStreamingConsumer):
            async def handle(self, body):
                await self.manager.acquire(self.session)
                raise Exception("Error")

        app = make_application(name="test", consumers={"test": (True, Consumer)})
        communicator = HttpCommunicator(app, "GET", "/sockjs/000/s1/test")
        response = await communicator.get_response()

        self.assertEqual(response["status"], 500)

        manager = sockjs.get_manager(app.routing, name='test')
        s1 = manager["s1"]
        self.assertFalse(manager.is_acquired(s1))

    async def test_raw_websocket(self):
        communicator = WebsocketCommunicator(make_application(), "/sockjs/websocket")
        accepted, _ = await communicator.connect()
        self.assertTrue(accepted)

    async def test_raw_websocket_fail(self):
        app = make_application(disable_consumers=("websocket",))
        communicator = WebsocketCommunicator(app, "/sockjs/websocket")
        accepted, _ = await communicator.connect()
        self.assertFalse(accepted)
