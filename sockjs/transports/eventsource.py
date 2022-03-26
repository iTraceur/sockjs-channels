from .base import HttpStreamingConsumer
from .utils import CACHE_CONTROL, session_cookie


class EventsourceConsumer(HttpStreamingConsumer):
    maxsize = 131072  # 128K bytes

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.size = 0

    async def handle(self, body):
        headers = {
            b"Connection": b"keep-alive",
            b"Content-Type": b"text/event-stream",
            b"Cache-Control": CACHE_CONTROL,
        }
        headers.update(session_cookie(self.scope))
        await self.send_headers(status=200, headers=headers)

        await self.send_body(b"\r\n", more_body=True)

        await self.handle_session()

    async def send_message(self, payload, *, more_body=False):
        body = "".join(("data: ", payload, "\r\n\r\n")).encode("utf-8")
        if more_body:
            self.size += len(body)
            if self.size < self.maxsize:
                more_body = True
            else:
                more_body = False
        await self.send_body(body, more_body=more_body)
        return not more_body
