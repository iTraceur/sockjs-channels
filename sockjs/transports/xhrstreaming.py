from .base import HttpStreamingConsumer
from .utils import CACHE_CONTROL, session_cookie, cors_headers, cache_headers


class XHRStreamingConsumer(HttpStreamingConsumer):
    open_seq = "h" * 2048

    async def handle(self, body):
        headers = {
            b"Content-Type": b"application/javascript; charset=UTF-8",
            b"Cache-Control": CACHE_CONTROL,
        }
        headers.update(session_cookie(self.scope))
        headers.update(cors_headers(self.scope["headers"]))

        if self.scope["method"] == "OPTIONS":
            headers[b"Access-Control-Allow-Methods"] = b"OPTIONS, POST"
            headers.update(cache_headers())
            return await self.send_response(204, b"", headers=headers)

        headers[b"Connection"] = dict(self.scope["headers"]).get(b"connection", b"close")

        await self.send_headers(status=200, headers=headers)

        await self.send_message(self.open_seq, more_body=True)

        await self.handle_session()
