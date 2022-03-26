from .base import HttpStreamingConsumer
from .utils import CACHE_CONTROL, session_cookie, cors_headers, cache_headers


class XHRConsumer(HttpStreamingConsumer):
    maxsize = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.size = 0

    async def handle(self, body):
        if self.scope["method"] == "OPTIONS":
            headers = {
                b"Content-Type": b"application/javascript; charset=UTF-8",
                b"Access-Control-Allow-Methods": b"OPTIONS, POST",
            }
            headers.update(session_cookie(self.scope))
            headers.update(cors_headers(self.scope["headers"]))
            headers.update(cache_headers())
            return await self.send_response(204, b"", headers=headers)

        headers = {
            b"Connection": b"keep-alive",
            b"Content-Type": b"application/javascript; charset=UTF-8",
            b"Cache-Control": CACHE_CONTROL,
        }
        headers.update(session_cookie(self.scope))
        headers.update(cors_headers(self.scope["headers"]))

        await self.send_headers(status=200, headers=headers)

        await self.handle_session()
