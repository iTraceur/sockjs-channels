import asyncio
import inspect
import logging
import random
from collections import namedtuple

from asgiref.sync import sync_to_async, async_to_sync
from channels.exceptions import StopConsumer
from django.urls import re_path

try:
    from threading import _register_atexit as register_atexit
except:
    from atexit import register as register_atexit

from . import transports
from .constants import (
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_SESSION_TIMEOUT,
    DEFAULT_GC_INTERVAL,
    SOCKJS_CDN
)
from .session import SessionManager

logger = logging.getLogger("sockjs")

Routing = namedtuple("Routing", ["http", "websocket", "config"], defaults=([], [], {}))


def get_manager(routing, name):
    return routing.config["__sockjs_managers__"][name]


def gen_endpoint_name():
    return "n" + str(random.randint(1000, 9999))


def teardown_session_manager(session_manager):
    async_to_sync(session_manager.clear)()


def add_endpoint(
        routing,
        handler,
        *,
        name="",
        prefix="sockjs",
        consumers=transports.consumers,
        disable_consumers=(),
        sockjs_cdn=SOCKJS_CDN,
        cookie_needed=True,
        manager=None,
        heartbeat_interval=DEFAULT_HEARTBEAT_INTERVAL,
        session_timeout=DEFAULT_SESSION_TIMEOUT,
        gc_interval=DEFAULT_GC_INTERVAL,
        debug=False
):
    assert callable(handler), handler
    if not asyncio.iscoroutinefunction(handler) and not inspect.isgeneratorfunction(handler):
        handler = sync_to_async(handler)

    if not name:
        name = gen_endpoint_name()

    # set session manager
    if manager is None:
        manager = SessionManager(name, handler,
                                 heartbeat_interval=heartbeat_interval,
                                 session_timeout=session_timeout,
                                 gc_interval=gc_interval,
                                 debug=debug)

    if manager.name != name:
        raise ValueError("Session manage must have same name as sockjs route")

    managers = routing.config.setdefault("__sockjs_managers__", {})
    if name in managers:
        raise ValueError('SockJS "%s" route already registered' % name)

    managers[name] = manager

    # register urls
    route = SockJSRoute(manager, consumers, disable_consumers)

    if prefix.endswith("/"):
        prefix = prefix[:-1]

    route_name = "sockjs-url-%s-greeting" % name
    routing.http.append(re_path(r"^%s$" % prefix, transports.GreetingConsumer.as_asgi(), name=route_name))

    route_name = "sockjs-url-%s" % name
    routing.http.append(re_path(r"^%s/$" % prefix, transports.GreetingConsumer.as_asgi(), name=route_name))

    route_name = "sockjs-info-%s" % name
    routing.http.append(re_path(r"^%s/info$" % prefix,
                                transports.InfoConsumer.as_asgi(cookie_needed=cookie_needed,
                                                                disable_consumers=disable_consumers),
                                name=route_name))

    route_name = "sockjs-iframe-%s" % name
    routing.http.append(re_path(r"^%s/iframe.html$" % prefix,
                                transports.IframeConsumer.as_asgi(sockjs_cdn=sockjs_cdn),
                                name=route_name))

    route_name = "sockjs-iframe-ver-%s" % name
    routing.http.append(re_path(r"^%s/iframe(?P<version>[\w-]+).html$" % prefix,
                                transports.IframeConsumer.as_asgi(sockjs_cdn=sockjs_cdn),
                                name=route_name))

    route_name = "sockjs-%s" % name
    routing.http.append(re_path(r"^%s/(?P<server>.*)/(?P<sid>.*)/(?P<cid>[\w-]+)$" % prefix,
                                route.handler, name=route_name))
    routing.websocket.append(re_path(r"^%s/(?P<server>.+)/(?P<sid>.+)/(?P<cid>[\w-]+)$" % prefix,
                                     route.handler, name=route_name))

    route_name = "sockjs-websocket-%s" % name
    routing.websocket.append(re_path(r"^%s/websocket$" % prefix, route.websocket, name=route_name))

    register_atexit(teardown_session_manager, manager)


class SockJSRoute(object):
    def __init__(self, manager, consumers, disable_consumers):
        self.manager = manager
        self.consumers = consumers
        self.disable_consumers = disable_consumers

    async def handler(self, scope, receive, send):
        kwargs = scope["url_route"]["kwargs"]
        server = kwargs["server"]
        sid = kwargs["sid"]
        cid = kwargs["cid"]
        if cid not in self.consumers or cid in self.disable_consumers:
            await self.handle_404(cid, send, b"SockJS consumer handler not found.")
            return

        create, consumer = self.consumers[cid]

        # session manager
        manager = self.manager
        if not manager.started:
            manager.start()

        if not sid or "." in sid or "." in server:
            await self.handle_404(cid, send, b"SockJS bad route.")
            return

        try:
            session = manager.get(sid, create, scope=scope)
        except KeyError:
            await self.handle_404(cid, send, b"SockJS session not found.")
            return

        try:
            c = consumer.as_asgi(manager=manager, session=session, create=create)
            return await c(scope, receive, send)
        except asyncio.CancelledError:
            pass
        except StopConsumer as exc:
            msg = "Server Exception in Consumer handler: %s" % str(exc)
            logger.exception(msg)

    async def websocket(self, scope, receive, send):
        if "websocket" not in self.consumers or "websocket" in self.disable_consumers:
            await self.handle_404("websocket", send, b"SockJS consumer handler not found.")
            return

        # session manager
        manager = self.manager
        if not manager.started:
            manager.start()

        sid = "%0.9d" % random.randint(1, 2147483647)

        session = manager.get(sid, True, scope=scope)

        c = transports.RawWebsocketConsumer.as_asgi(manager=manager, session=session)
        try:
            return await c(scope, receive, send)
        except asyncio.CancelledError:
            raise
        except StopConsumer as exc:
            msg = "Server Exception in Consumer handler: %s" % str(exc)
            logger.exception(msg)

    async def handle_404(self, cid, send, body):
        if cid == "websocket":
            await send({"type": "websocket.close", "code": 10001})
        else:
            headers = [
                (b"Content-Type", b"text/plain; charset=UTF-8"),
                (b"Content-Length", str(len(body)).encode("utf-8"))
            ]
            await send({"type": "http.response.start", "status": 404, "headers": headers})
            await send({"type": "http.response.body", "body": body, "more_body": False})


def make_routing(
        handler,
        *,
        name="sockjs",
        prefix="sockjs",
        consumers=transports.consumers,
        disable_consumers=(),
        sockjs_cdn=SOCKJS_CDN,
        cookie_needed=True,
        manager=None,
        heartbeat_interval=DEFAULT_HEARTBEAT_INTERVAL,
        session_timeout=DEFAULT_SESSION_TIMEOUT,
        gc_interval=DEFAULT_GC_INTERVAL,
        debug=False
):
    routing = Routing(http=[], websocket=[], config={})
    add_endpoint(routing, handler, name=name, prefix=prefix,
                 consumers=consumers, disable_consumers=disable_consumers,
                 sockjs_cdn=sockjs_cdn, cookie_needed=cookie_needed,
                 manager=manager, heartbeat_interval=heartbeat_interval,
                 session_timeout=session_timeout, gc_interval=gc_interval, debug=debug)

    return routing
