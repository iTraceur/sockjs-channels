import json
import re

from django import http
from django.core import exceptions

from .base import HttpStreamingConsumer
from .utils import CACHE_CONTROL, session_cookie, cors_headers

PRELUDE1 = """<!doctype html>
<html><head>
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
</head><body><h2>Don"t panic!</h2>
  <script>
    document.domain = document.domain;
    var c = parent."""

PRELUDE2 = """;
    c.start();
    function p(d) {c.message(d);};
    window.onload = function() {c.stop();};
  </script>"""


class HTMLFileConsumer(HttpStreamingConsumer):
    maxsize = 131072  # 128K bytes
    check_callback = re.compile(r"^[a-zA-Z0-9_.]+$")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.size = 0

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

        await self.send_body("".join((PRELUDE1, callback, PRELUDE2)).encode("utf-8"), more_body=True)

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
