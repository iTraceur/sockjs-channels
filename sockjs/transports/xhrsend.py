from django.core import exceptions

from .base import HttpStreamingConsumer
from .utils import CACHE_CONTROL, session_cookie, cors_headers, cache_headers
from ..protocol import loads


class XHRSendConsumer(HttpStreamingConsumer):
    async def handle(self, body):
        allowed_methods = ("POST", "OPTIONS")
        if self.scope["method"] not in allowed_methods:
            headers = {
                b"Connection": b"close",
                b"Access-Control-Allow-Methods": ','.join(allowed_methods).encode("utf-8"),
                b"Content-Type": b"text/plain; charset=UTF-8",
            }
            msg = "Method `%s` is not allowed, allowed methods: %s" % (self.scope["method"], ','.join(allowed_methods))
            return await self.send_response(403, msg.encode("utf-8"), headers=headers)

        if self.scope["method"] == "OPTIONS":
            headers = {
                b"Access-Control-Allow-Methods": b"OPTIONS, POST",
                b"Content-Type": b"application/javascript; charset=UTF-8",
            }
            headers.update(session_cookie(self.scope))
            headers.update(cors_headers(self.scope["headers"]))
            headers.update(cache_headers())
            return await self.send_response(204, b"", headers=headers)

        if not body:
            raise exceptions.BadRequest("Payload expected.")

        try:
            messages = loads(body)
        except Exception:
            raise exceptions.BadRequest("Broken JSON encoding.")

        headers = {
            b"Connection": b"keep-alive",
            b"Content-Type": b"text/plain; charset=UTF-8",
            b"Cache-Control": CACHE_CONTROL,
        }
        headers.update(session_cookie(self.scope))
        headers.update(cors_headers(self.scope["headers"]))

        await self.send_headers(status=204, headers=headers)

        await self.session.remote_messages(messages)

        await self.send_body(b"[]")
