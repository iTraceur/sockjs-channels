import asyncio
import inspect
from unittest import mock
from unittest.mock import sentinel
from urllib.parse import urlparse, unquote

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import re_path

import sockjs
from sockjs import Session, SessionManager
from sockjs.session import DEFAULT_SESSION_TIMEOUT


def make_mocked_coroutine(return_value=sentinel, raise_exception=sentinel):
    """Creates a coroutine mock."""

    async def mock_coroutine(*args, **kwargs):
        if raise_exception is not sentinel:
            raise raise_exception
        if not inspect.isawaitable(return_value):
            return return_value
        return await return_value

    return mock.Mock(wraps=mock_coroutine)


def make_future(value, make_mock=True):
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    future.set_result(value)

    if make_mock:
        m = mock.Mock()
        m.return_value = future
        return m
    else:
        return future


def make_scope(method, path, headers=None):
    parsed = urlparse(path)
    return {
        "type": "http",
        "http_version": "1.1",
        "method": method.upper(),
        "path": unquote(parsed.path),
        "query_string": parsed.query.encode("utf-8"),
        "headers": headers or [],
    }


def make_websocket_scope(path, headers=None, subprotocols=None):
    parsed = urlparse(path)
    return {
        "type": "websocket",
        "path": unquote(parsed.path),
        "query_string": parsed.query.encode("utf-8"),
        "headers": headers or [],
        "subprotocols": subprotocols or [],
    }


def make_handler(result, exc=False):
    if result is None:
        result = []
    output = result

    async def async_handler(msg, session):
        if exc:
            raise ValueError((msg, session))
        output.append((msg, session))

    return async_handler


def make_session(name="test", handler=None, scope=None, timeout=DEFAULT_SESSION_TIMEOUT, result=None):
    if scope is None:
        scope = make_scope("GET", path="/sockjs/000/000000/test")
    if handler is None:
        handler = make_handler(result)
    return Session(name, handler, scope, timeout=timeout, debug=True)


def make_manager(handler=None):
    if handler is None:
        handler = make_handler([])
    return SessionManager("sm", handler, debug=True)


def make_application(name="test", prefix="sockjs", consumers=None, disable_consumers=(), handler=None):
    if handler is None:
        handler = make_handler([])

    if consumers:
        routing = sockjs.make_routing(handler, name=name, prefix=prefix,
                                      consumers=consumers, disable_consumers=disable_consumers)
    else:
        routing = sockjs.make_routing(handler, name=name, prefix=prefix,
                                      disable_consumers=disable_consumers)

    routing.http.append(re_path(r'', get_asgi_application()))

    application = ProtocolTypeRouter({
        'http': AuthMiddlewareStack(
            URLRouter([
                *routing.http,
            ])
        ),
        'websocket': AuthMiddlewareStack(
            URLRouter([
                *routing.websocket
            ])
        ),
    })
    application.routing = routing
    return application
