import asyncio

from .base import BaseWebsocketConsumer
from ..exceptions import SessionIsClosed, SessionIsAcquired
from ..protocol import loads, STATE_CLOSED, FRAME_CLOSE, close_frame, STATE_CLOSING


class WebsocketConsumer(BaseWebsocketConsumer):
    session_loop_task = None

    async def connect(self):
        await self.accept()

        await self.handle_session()

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = text_data or bytes_data.decode("utf-8")
            if payload.startswith("["):
                payload = payload[1:-1]

            data = loads(payload)
            await self.session.remote_message(data)
        except Exception as exc:
            await self.session.remote_close(exc=exc)
            await self.session.remote_closed()
            await self.close()

    async def handle_session(self):
        if self.session.interrupted:
            await self.send(close_frame(1002, "Connection interrupted"))
        elif self.session.state in (STATE_CLOSING, STATE_CLOSED):
            await self.session.remote_closed()
            await self.send(close_frame(3000, "Go away!"))
            return

        try:
            await self.manager.acquire(self.session)
        except SessionIsAcquired:
            await self.send(close_frame(2010, "Another connection still open"))
            return
        except Exception as exc:
            await self.session.remote_close(exc=exc)
            await self.session.remote_closed()
            await self.send(close_frame(3000, "Go away!"))
            await self.close(code=3000)
            return

        self.session_loop_task = asyncio.ensure_future(self.session_loop())

    async def session_loop(self):
        try:
            while True:
                try:
                    frame, payload = await self.session.wait()
                except SessionIsClosed:
                    break

                await self.send(payload)

                if frame == FRAME_CLOSE:
                    try:
                        await self.close(code=3000)
                    finally:
                        await self.session.remote_closed()
        except BaseException as exc:
            await self.session.remote_close(exc=exc)
            await self.session.remote_closed()
        finally:
            await self.manager.release(self.session)

    async def disconnect(self, code):
        await self.session.remote_closed()
        await self.manager.release(self.session)

        if self.session_loop_task is not None:
            self.session_loop_task.cancel()
            self.session_loop_task = None
