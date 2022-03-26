import re
from urllib.parse import unquote_plus

from django import http
from django.core import exceptions

from .base import HttpStreamingConsumer
from .utils import CACHE_CONTROL, session_cookie, cors_headers
from ..protocol import loads, dumps


class JSONPollingConsumer(HttpStreamingConsumer):
    check_callback = re.compile(r"^[a-zA-Z0-9_.]+$")
    callback = ""

    async def handle(self, body):
        if self.scope["method"] == "GET":
            query_params = http.QueryDict(self.scope.get("query_string", ""))
            callback = self.callback = query_params.get("c", None)
            if callback is None:
                await self.session.remote_closed()
                raise exceptions.BadRequest('"callback" parameter required')
            elif not self.check_callback.match(callback):
                await self.session.remote_closed()
                raise exceptions.BadRequest('invalid "callback" parameter')

            headers = {
                b"Content-Type": b"application/javascript; charset=UTF-8",
                b"Cache-Control": CACHE_CONTROL,
                b"Connection": b"keep-alive",
            }
            headers.update(session_cookie(self.scope))
            headers.update(cors_headers(self.scope["headers"]))

            await self.send_headers(status=200, headers=headers)

            await self.handle_session()
        elif self.scope["method"] == "POST":
            content_type = dict(self.scope["headers"]).get(b"content-type", b"").decode().lower()
            if content_type == "application/x-www-form-urlencoded":
                if not body.startswith(b"d="):
                    raise exceptions.BadRequest("Payload expected.")

                body = unquote_plus(body[2:].decode())
            else:
                body = body.decode()

            if not body:
                raise exceptions.BadRequest("Payload expected.")

            try:
                messages = loads(body)
            except Exception:
                raise exceptions.BadRequest("Broken JSON encoding.")

            headers = {
                b"Content-Type": b"text/html; charset=UTF-8",
                b"Cache-Control": CACHE_CONTROL,
                b"Connection": b"keep-alive",
            }
            headers.update(session_cookie(self.scope))
            await self.send_headers(status=200, headers=headers)

            await self.session.remote_messages(messages)

            await self.send_message("ok")
        else:
            headers = {
                b"Connection": b"close",
                b"Access-Control-Allow-Methods": b"GET,POST",
                b"Content-Type": b"text/plain; charset=UTF-8",
            }
            msg = "No support for such method:{%s}" % self.scope["method"]
            return await self.send_response(400, msg.encode("utf-8"), headers=headers)

    async def send_message(self, payload, *, more_body=False):
        body = "/**/%s(%s);\r\n" % (self.callback, dumps(payload))
        await self.send_body(body.encode("utf-8"), more_body=False)
        return True
