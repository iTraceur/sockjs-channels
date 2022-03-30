from .base import HttpStreamingConsumer
from .utils import CACHE_CONTROL, session_cookie, cors_headers, cache_headers


class XHRConsumer(HttpStreamingConsumer):
    maxsize = 0

    async def handle(self, body):
        headers = {
            b"Content-Type": b"application/javascript; charset=UTF-8",
        }
        headers.update(session_cookie(self.scope))
        headers.update(cors_headers(self.scope["headers"]))

        if self.scope["method"] == "OPTIONS":
            headers.update(cache_headers())
            headers[b"Access-Control-Allow-Methods"] = b"OPTIONS, POST"
            return await self.send_response(204, b"", headers=headers)

        headers.update({
            b"Connection": b"keep-alive",
            b"Cache-Control": CACHE_CONTROL,
        })

        await self.send_headers(status=200, headers=headers)

        await self.handle_session()
