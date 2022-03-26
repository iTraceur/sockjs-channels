import asyncio
import logging
import warnings
from collections import deque
from datetime import datetime

from .constants import DEFAULT_SESSION_TIMEOUT, DEFAULT_HEARTBEAT_INTERVAL, DEFAULT_GC_INTERVAL
from .exceptions import SessionIsAcquired, SessionIsClosed
from .protocol import FRAME_MESSAGE, FRAME_MESSAGE_BLOB, FRAME_HEARTBEAT
from .protocol import FRAME_OPEN, FRAME_CLOSE
from .protocol import MSG_CLOSE, MSG_MESSAGE
from .protocol import STATE_NEW, STATE_OPEN, STATE_CLOSING, STATE_CLOSED
from .protocol import SockjsMessage, OpenMessage, ClosedMessage
from .protocol import close_frame, message_frame, messages_frame

logger = logging.getLogger("sockjs")


class Session(object):
    """ SockJS session object

    ``state``: Session state

    ``manager``: Session manager that hold this session

    ``acquired``: Acquired state, indicates that consumer is using session

    ``timeout``: Session timeout

    """

    scope = None
    manager = None
    acquired = False
    state = STATE_NEW
    interrupted = False
    exception = None

    _heartbeat_timer = None  # heartbeat event loop timer
    _heartbeat_future_task = None  # heartbeat task
    _heartbeat_consumed = True

    def __init__(self, sid, handler, scope, *, timeout=DEFAULT_SESSION_TIMEOUT,
                 heartbeat_interval=DEFAULT_HEARTBEAT_INTERVAL, debug=False):
        self.id = sid
        self.handler = handler
        self.scope = scope
        self.expired = False
        self.timeout = timeout
        self.heartbeat_interval = heartbeat_interval
        self.expires = datetime.now() + timeout

        self._hits = 0
        self._heartbeats = 0
        self._heartbeat_consumer = False
        self._debug = debug
        self._waiter = None
        self._queue = deque()

    def __str__(self):
        result = ["id=%r" % (self.id,)]

        if self.state == STATE_OPEN:
            result.append("connected")
        elif self.state == STATE_CLOSED:
            result.append("closed")
        else:
            result.append("disconnected")

        if self.acquired:
            result.append("acquired")

        if self.message_length:
            result.append("queue[%s]" % self.message_length)
        if self._hits:
            result.append("hits=%s" % self._hits)
        if self._heartbeats:
            result.append("heartbeats=%s" % self._heartbeats)

        return " ".join(result)

    @property
    def message_length(self):
        return len(self._queue)

    def _tick(self, timeout=None):
        if timeout is None:
            self.expires = datetime.now() + self.timeout
        else:
            self.expires = datetime.now() + timeout

    async def acquire(self, scope, manager, heartbeat=True):
        self.acquired = True
        self.scope = scope
        self.manager = manager
        self._heartbeat_consumer = heartbeat

        self._tick()
        self._hits += 1

        if self.state == STATE_NEW:
            logger.debug("open session: %s", self.id)
            self.state = STATE_OPEN
            self._feed(FRAME_OPEN, FRAME_OPEN)
            try:
                await self.handler(OpenMessage, self)
                self.start_heartbeat()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.state = STATE_CLOSING
                self.exception = exc
                self.interrupted = True
                self._feed(FRAME_CLOSE, (3000, "Internal error"))
                logger.exception("Exception in open session handling.")

    def release(self):
        self.acquired = False
        self.scope = None
        self.manager = None

    def start_heartbeat(self):
        if self._heartbeat_consumer and not self._heartbeat_timer:
            loop = asyncio.get_event_loop()
            self._heartbeat_timer = loop.call_later(self.heartbeat_interval, self._heartbeat)

    def stop_heartbeat(self):
        if self._heartbeat_timer is not None:
            self._heartbeat_timer.cancel()
            self._heartbeat_timer = None

    def _heartbeat(self):
        # If the last heartbeat was not consumed, the client was closed.
        if not self._heartbeat_consumed:
            asyncio.ensure_future(self.remote_closed())
            return

        if self.state != STATE_OPEN:
            self.stop_heartbeat()
            return

        self._heartbeats += 1
        self._feed(FRAME_HEARTBEAT, FRAME_HEARTBEAT)
        self._heartbeat_consumed = False

        loop = asyncio.get_event_loop()
        self._heartbeat_timer = loop.call_later(self.heartbeat_interval, self._heartbeat)

    def _feed(self, frame, data):
        # pack messages
        if frame == FRAME_MESSAGE:
            if self._queue and self._queue[-1][0] == FRAME_MESSAGE:
                self._queue[-1][1].append(data)
            else:
                self._queue.append((frame, [data]))
        else:
            self._queue.append((frame, data))

        # notify waiter
        self.notify_waiter()

    async def wait(self, pack=True):
        if not self._queue and self.state != STATE_CLOSED:
            assert not self._waiter
            loop = asyncio.get_event_loop()
            self._waiter = loop.create_future()
            await self._waiter

        if self._queue:
            frame, message = self._queue.popleft()

            if frame == FRAME_HEARTBEAT:
                self._heartbeat_consumed = True

            if pack:
                if frame == FRAME_CLOSE:
                    return FRAME_CLOSE, close_frame(*message)
                elif frame == FRAME_MESSAGE:
                    return FRAME_MESSAGE, messages_frame(message)

            return frame, message
        else:
            raise SessionIsClosed()

    def notify_waiter(self):
        waiter = self._waiter
        if waiter is not None:
            self._waiter = None
            if not waiter.cancelled():
                waiter.set_result(True)

    def send(self, message):
        """send message to client."""
        assert isinstance(message, str), "String is required"

        if self._debug:
            logger.info("outgoing message: %s, %s", self.id, str(message)[:200])

        if self.state != STATE_OPEN:
            return

        self._feed(FRAME_MESSAGE, message)

    def send_frame(self, frame):
        """send message frame to client."""
        if self._debug:
            logger.info("outgoing message: %s, %s", self.id, frame[:200])

        if self.state != STATE_OPEN:
            return

        self._feed(FRAME_MESSAGE_BLOB, frame)

    def expire(self):
        """Manually expire a session."""
        self.expired = True

        self.stop_heartbeat()

    async def remote_message(self, message):
        logger.debug("incoming message: %s, %s", self.id, message[:200])
        self._tick()

        try:
            await self.handler(SockjsMessage(MSG_MESSAGE, message), self)
        except:
            logger.exception("Exception in message handler.")

    async def remote_messages(self, messages):
        self._tick()

        for message in messages:
            logger.debug("incoming message: %s, %s", self.id, message[:200])
            try:
                await self.handler(SockjsMessage(MSG_MESSAGE, message), self)
            except:
                logger.exception("Exception in message handler.")

    async def remote_close(self, exc=None):
        """close session from remote."""
        if self.state in (STATE_CLOSING, STATE_CLOSED):
            return

        logger.info("close session: %s", self.id)
        self.state = STATE_CLOSING
        if exc is not None:
            self.exception = exc
            self.interrupted = True
        try:
            await self.handler(SockjsMessage(MSG_CLOSE, exc), self)
        except:
            logger.exception("Exception in close handler.")

        self.stop_heartbeat()

    async def remote_closed(self):
        if self.state == STATE_CLOSED:
            return

        logger.info("session closed: %s", self.id)
        self.state = STATE_CLOSED
        self.expire()
        try:
            await self.handler(ClosedMessage, self)
        except:
            logger.exception("Exception in closed handler.")

        # notify waiter
        self.notify_waiter()

    def close(self, code=3000, reason="Go away!"):
        """close session"""
        if self.state in (STATE_CLOSING, STATE_CLOSED):
            return

        if self._debug:
            logger.debug("close session: %s", self.id)

        self.state = STATE_CLOSING
        self._feed(FRAME_CLOSE, (code, reason))
        self.stop_heartbeat()


empty = object()


class SessionManager(dict):
    """A basic session manager."""

    _gc_timer = None  # gc event loop timer
    _gc_future_task = None  # gc task

    def __init__(self,
                 name,
                 handler,
                 heartbeat_interval=DEFAULT_HEARTBEAT_INTERVAL,
                 session_timeout=DEFAULT_SESSION_TIMEOUT,
                 gc_interval=DEFAULT_GC_INTERVAL,
                 debug=False):
        super().__init__()
        self.name = name
        self.route_name = "sockjs-url-%s" % name
        self.handler = handler
        self.factory = Session
        self.gc_interval = gc_interval
        self.heartbeat_interval = heartbeat_interval
        self.session_timeout = session_timeout
        self.debug = debug

        self._acquired_map = {}
        self._sessions = []

    def __str__(self):
        return "SessionManager<%s>" % self.route_name

    @property
    def started(self):
        return self._gc_timer is not None

    def start(self):
        if not self._gc_timer:
            loop = asyncio.get_event_loop()
            self._gc_timer = loop.call_later(self.gc_interval, self._gc)

    def stop(self):
        if self._gc_timer is not None:
            self._gc_timer.cancel()
            self._gc_timer = None
        if self._gc_future_task is not None:
            self._gc_future_task.cancel()
            self._gc_future_task = None

    def _gc(self):
        if self._gc_future_task is None:
            self._gc_future_task = asyncio.ensure_future(self._gc_task())

    async def _gc_task(self):
        if self._sessions:
            now = datetime.now()

            idx = 0
            while idx < len(self._sessions):
                session = self._sessions[idx]

                if session.expires < now or session.expired:
                    # Session is to be GC"d immedietely
                    if session.id in self._acquired_map:
                        await self.release(session)
                    if session.state == STATE_OPEN:
                        await session.remote_close()
                    if session.state == STATE_CLOSING:
                        await session.remote_closed()

                    del self[session.id]
                    del self._sessions[idx]
                    continue

                idx += 1

        self._gc_future_task = None
        loop = asyncio.get_event_loop()
        self._gc_timer = loop.call_later(self.gc_interval, self._gc)

    def _add(self, session):
        if session.expired:
            raise ValueError("Can not add expired session")

        session.manager = self

        self[session.id] = session
        self._sessions.append(session)
        return session

    def get(self, sid, create=False, scope=None, default=empty):
        session = super().get(sid, None)
        if session is None:
            if create:
                session = self._add(
                    self.factory(sid, self.handler, scope, timeout=self.session_timeout,
                                 heartbeat_interval=self.heartbeat_interval, debug=self.debug)
                )
            else:
                if default is not empty:
                    return default
                raise KeyError(sid)

        return session

    async def acquire(self, scope, session):
        sid = session.id

        if sid in self._acquired_map:
            raise SessionIsAcquired("Another connection still open")
        if sid not in self:
            raise KeyError("Unknown session")

        await session.acquire(scope, self)

        self._acquired_map[sid] = True
        return session

    def is_acquired(self, session):
        return session.id in self._acquired_map

    async def release(self, session):
        if session.id in self._acquired_map:
            session.release()
            del self._acquired_map[session.id]

    def active_sessions(self):
        for session in list(self.values()):
            if not session.expired:
                yield session

    async def clear(self):
        """Manually expire all _sessions in the pool."""
        for session in list(self.values()):
            if session.state != STATE_CLOSED:
                await session.remote_closed()

        self._sessions.clear()
        super().clear()

    def broadcast(self, message):
        blob = message_frame(message)
        for session in list(self.values()):
            if not session.expired:
                session.send_frame(blob)

    def __del__(self):
        if len(self._sessions):
            warnings.warn(
                "Unclosed _sessions! "
                "Please call `await SessionManager.clear()` before del",
                RuntimeWarning,
            )

        self.stop()
