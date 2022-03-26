from .base import GreetingConsumer, InfoConsumer, IframeConsumer
from .eventsource import EventsourceConsumer
from .htmlfile import HTMLFileConsumer
from .jsonp import JSONPollingConsumer
from .rawwebsocket import RawWebsocketConsumer
from .websocket import WebsocketConsumer
from .xhr import XHRConsumer
from .xhrsend import XHRSendConsumer
from .xhrstreaming import XHRStreamingConsumer

consumers = {
    "websocket": (True, WebsocketConsumer),
    "xhr": (True, XHRConsumer),
    "xhr_send": (False, XHRSendConsumer),
    "xhr_streaming": (True, XHRStreamingConsumer),
    "jsonp": (True, JSONPollingConsumer),
    "jsonp_send": (False, JSONPollingConsumer),
    "htmlfile": (True, HTMLFileConsumer),
    "eventsource": (True, EventsourceConsumer),
}
