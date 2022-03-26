import asyncio

from .base import BaseWebsocketConsumer
from ..exceptions import SessionIsClosed
from ..protocol import FRAME_CLOSE, FRAME_MESSAGE, FRAME_MESSAGE_BLOB


class RawWebsocketConsumer(BaseWebsocketConsumer):
    session_loop_task = None

    async def connect(self):
        await self.accept()

        await self.handle_session()

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        await self.session.remote_message(text_data)

    async def handle_session(self):
        try:
            await self.manager.acquire(self.scope, self.session)
        except Exception as exc:
            await self.session.remote_close(str(exc))
            await self.close(code=3000)
            return

        self.session_loop_task = asyncio.ensure_future(self.session_loop())

    async def session_loop(self):

        try:
            while True:
                try:
                    frame, payload = await self.session.wait(pack=False)
                except SessionIsClosed:
                    break

                if frame == FRAME_MESSAGE:
                    for data in payload:
                        await self.send(data)
                elif frame == FRAME_MESSAGE_BLOB:
                    payload = payload[1:]
                    if payload.startswith("["):
                        payload = payload[1:-1]

                    await self.send(payload)
                elif frame == FRAME_CLOSE:
                    try:
                        await self.close(code=3000)
                    finally:
                        await self.session.remote_closed()
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            await self.session.remote_close(str(exc))
        finally:
            await self.manager.release(self.session)

    async def disconnect(self, code):
        await self.session.remote_closed()

        if self.session_loop_task is not None:
            self.session_loop_task.cancel()
            self.session_loop_task = None
