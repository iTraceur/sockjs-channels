import asyncio

from .base import BaseWebsocketConsumer
from ..exceptions import SessionIsClosed, SessionIsAcquired
from ..protocol import STATE_CLOSED, FRAME_CLOSE, close_frame, loads


class WebsocketConsumer(BaseWebsocketConsumer):
    session_loop_task = None

    async def connect(self):
        await self.accept()

        await self.handle_session()

    async def receive(self, text_data=None, bytes_data=None):
        try:
            if text_data.startswith("["):
                text_data = text_data[1:-1]

            data = loads(text_data)
            await self.session.remote_message(data)
        except Exception as exc:
            await self.session.remote_close(exc)
            await self.session.remote_closed()
            await self.close()

    async def handle_session(self):
        if self.session.interrupted:
            await self.send(close_frame(1002, "Connection interrupted"))
        elif self.session.state == STATE_CLOSED:
            await self.send(close_frame(3000, "Go away!"))
            return

        try:
            await self.manager.acquire(self.scope, self.session)
        except SessionIsAcquired:
            await self.send(close_frame(2010, "Another connection still open"))
            return
        except Exception as exc:
            await self.session.remote_close(str(exc))
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

                try:
                    await self.send(payload)
                except OSError:
                    pass  # ignore "cannot write to closed consumer"

                if frame == FRAME_CLOSE:
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
        await self.manager.release(self.session)

        if self.session_loop_task is not None:
            self.session_loop_task.cancel()
            self.session_loop_task = None
