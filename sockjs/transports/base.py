import asyncio
import json
import random

from channels.exceptions import StopConsumer
from channels.generic.http import AsyncHttpConsumer
from channels.generic.websocket import AsyncWebsocketConsumer

from .utils import CACHE_CONTROL, cors_headers, session_cookie, cache_headers
from ..constants import SOCKJS_CDN
from ..exceptions import SessionIsAcquired, SessionIsClosed
from ..protocol import FRAME_MESSAGE, FRAME_CLOSE
from ..protocol import IFRAME_HTML, IFRAME_MD5
from ..protocol import STATE_CLOSING, STATE_CLOSED
from ..protocol import close_frame


class GreetingConsumer(AsyncHttpConsumer):
    async def handle(self, body):
        payload = b"Welcome to SockJS!\n"

        headers = {
            b"Connection": b"keep-alive",
            b"Content-Type": b"text/plain; charset=UTF-8",
            b"Content-Length": str(len(payload)).encode("utf-8"),
            b"Cache-Control": CACHE_CONTROL,
        }
        headers.update(session_cookie(self.scope))
        headers.update(cors_headers(self.scope["headers"]))

        await self.send_response(200, payload, headers=headers)


class InfoConsumer(AsyncHttpConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cookie_needed = kwargs.get("cookie_needed", True)
        self.disable_consumers = kwargs.get("disable_consumers", [])

    async def handle(self, body):
        info = {"entropy": random.randint(1, 2147483647),
                "websocket": "websocket" not in self.disable_consumers,
                "cookie_needed": self.cookie_needed,
                "origins": ["*:*"]}

        payload = json.dumps(info).encode("utf-8")

        headers = {
            b"Connection": b"keep-alive",
            b"Content-Type": b"application/json; charset=UTF-8",
            b"Content-Length": str(len(payload)).encode("utf-8"),
            b"Cache-Control": CACHE_CONTROL,
        }
        headers.update(session_cookie(self.scope))
        headers.update(cors_headers(self.scope["headers"]))

        await self.send_response(200, payload, headers=headers)


class IframeConsumer(AsyncHttpConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        sockjs_cdn = kwargs.get("sockjs_cdn", SOCKJS_CDN)
        self.iframe_html = (IFRAME_HTML % sockjs_cdn).encode("utf-8")
        self.iframe_html_hxd = IFRAME_MD5.encode("utf-8")

    async def handle(self, body):
        headers = dict(self.scope["headers"])
        cached = headers.get(b"IF-NONE-MATCH", None)
        if cached:
            headers = {b"Content-Type": b""}
            headers.update(cache_headers())
            await self.send_response(304, b"", headers=headers)
            return

        headers = {
            b"Connection": b"keep-alive",
            b"Content-Type": b"text/html; charset=UTF-8",
            b"Content-Length": str(len(self.iframe_html)).encode("utf-8"),
            b"ETag": self.iframe_html_hxd,
        }
        headers.update(cache_headers())
        await self.send_response(200, self.iframe_html, headers=headers)


class BaseWebsocketConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        manager = kwargs.pop("manager", None)
        session = kwargs.pop("session", None)
        create = kwargs.pop("create", False)

        super().__init__(*args, **kwargs)

        if not manager or not session:
            raise StopConsumer()

        self.manager = manager
        self.session = session
        self.create = create


class HttpStreamingConsumer(AsyncHttpConsumer):
    maxsize = 131072  # 128K bytes
    timeout = None  # timeout to wait for message

    def __init__(self, *args, **kwargs):
        manager = kwargs.pop("manager", None)
        session = kwargs.pop("session", None)
        create = kwargs.pop("create", False)

        super().__init__(*args, **kwargs)

        if not manager or not session:
            raise StopConsumer()

        self.manager = manager
        self.session = session
        self.create = create
        self.size = 0

    async def handle(self, body):
        raise NotImplementedError(
            "Subclasses of HttpStreamingConsumer must provide a handle() method."
        )

    async def http_request(self, message):
        if "body" in message:
            self.body.append(message["body"])
        if not message.get("more_body"):
            try:
                await self.handle(b"".join(self.body))
            except BaseException as exc:
                await self.handle_exception(exc)

                if self.create and self.manager.is_acquired(self.session):
                    await self.manager.release(self.session)
            finally:
                await self.disconnect()
                raise StopConsumer()

    async def send_message(self, payload, *, more_body=False):
        body = (payload + "\n").encode("utf-8")
        if more_body:
            self.size += len(body)
            if self.size < self.maxsize:
                more_body = True
            else:
                more_body = False
        await self.send_body(body, more_body=more_body)
        stop_send = not more_body
        return stop_send

    async def handle_session(self):
        if self.session.interrupted:  # session was interrupted
            await self.send_message(close_frame(1002, "Connection interrupted"))
            return
        elif self.session.state in (STATE_CLOSING, STATE_CLOSED):  # session is closing or closed
            await self.session.remote_closed()
            await self.send_message(close_frame(3000, "Go away!"))
            return

        # acquire session
        try:
            await self.manager.acquire(self.scope, self.session)
        except SessionIsAcquired:
            await self.send_message(close_frame(2010, "Another connection still open"))
            return

        try:
            while True:
                if self.timeout:
                    try:
                        frame, payload = await asyncio.wait_for(self.session.wait(), timeout=self.timeout)
                    except asyncio.exceptions.TimeoutError:
                        frame, payload = FRAME_MESSAGE, "a[]"
                else:
                    frame, payload = await self.session.wait()

                if frame == FRAME_CLOSE:
                    await self.session.remote_closed()
                    await self.send_message(payload)
                    return
                else:
                    stop = await self.send_message(payload, more_body=True)
                    if stop:
                        break
        except SessionIsClosed:
            pass
        except (asyncio.CancelledError, StopConsumer) as exc:
            await self.session.remote_close(exc=exc)
            await self.session.remote_closed()
            raise
        finally:
            await self.manager.release(self.session)

    async def handle_exception(self, exc):
        body = str(exc).encode("utf-8")
        headers = [
            (b"Content-Type", b"text/plain; charset=UTF-8"),
            (b"Content-Length", len(body))
        ]
        await self.send_response(500, body, headers=headers)
