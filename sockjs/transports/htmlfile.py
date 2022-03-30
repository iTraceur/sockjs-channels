import json
import re

from django import http
from django.core import exceptions

from .base import HttpStreamingConsumer
from .utils import CACHE_CONTROL, session_cookie, cors_headers
from ..protocol import HTMLFILE_HTML


class HTMLFileConsumer(HttpStreamingConsumer):
    check_callback = re.compile(r"^[a-zA-Z0-9_.]+$")

    async def handle(self, body):
        query_params = http.QueryDict(self.scope.get("query_string", ""))
        callback = query_params.get("c", None)

        if callback is None:
            await self.session.remote_closed()
            raise exceptions.BadRequest('"callback" parameter required')
        elif not self.check_callback.match(callback):
            await self.session.remote_closed()
            raise exceptions.BadRequest('invalid "callback" parameter')

        headers = {
            b"Content-Type": b"text/html; charset=UTF-8",
            b"Cache-Control": CACHE_CONTROL,
            b"Connection": b"close",
        }
        headers.update(session_cookie(self.scope))
        headers.update(cors_headers(self.scope["headers"]))

        await self.send_headers(status=200, headers=headers)

        await self.send_body((HTMLFILE_HTML % callback).encode("utf-8"), more_body=True)

        await self.handle_session()

    async def send_message(self, payload, *, more_body=False):
        body = ("<script>\np(%s);\n</script>\r\n" % json.dumps(payload)).encode("utf-8")
        if more_body:
            self.size += len(body)
            if self.size < self.maxsize:
                more_body = True
            else:
                more_body = False
        await self.send_body(body, more_body=more_body)
        stop_send = not more_body
        return stop_send
