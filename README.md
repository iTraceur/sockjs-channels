# SockJS-Channels

`SockJS-Channels` is a server-side implementation of the [SockJS](http://sockjs.org) protocol for the [Django Channels](https://github.com/django/channels/) and was inspired by the [SockJS-aiohttp](https://github.com/aio-libs/sockjs/) project. SockJS-Channels interface is implemented as a ASGI routing, it runs inside a ASGI application rather than ASGI server. Its possible to create any number of different sockjs routings, ie `/sockjs/*` or `/chat-sockjs/*`. You can provide different session implementation and management for each sockjs routing.

## Requirements
* Python 3.6+
* Django 3.2+
* Channels 3.0.0+

## Installation
```bash
$ pip install sockjs-channels
```

## ASGI Routing
Here’s an example of `asgi.py` might looks like:
```python
import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import re_path

from sockjs import make_routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chat.settings')

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

from chat.views import chat_msg_handler

routing = make_routing(chat_msg_handler, name='chat')

# Add django's url routing
routing.http.append(re_path(r'', django_asgi_app))

application = ProtocolTypeRouter({
    'http': URLRouter([
        *routing.http
    ]),
    'websocket': URLRouter([
        *routing.websocket
    ])
})
```

## Supported Transports
* websocket
* xhr-streaming
* xhr-polling
* iframe-xhr-polling
* iframe-eventsource
* iframe-htmlfile
* jsonp-polling

## Examples
You can find a simple chat example in the sockjs-channels repository at github.

[https://github.com/iTraceur/sockjs-channels/tree/main/examples/chat](https://github.com/iTraceur/sockjs-channels/tree/main/examples/chat)

## License
sockjs-channels is offered under the MIT license.

## Test Coverage
```
Name                                Stmts   Miss Branch BrPart  Cover
---------------------------------------------------------------------
sockjs/__init__.py                     15      0      0      0   100%
sockjs/constants.py                     5      0      0      0   100%
sockjs/exceptions.py                    3      0      6      0   100%
sockjs/protocol.py                     36      0      0      0   100%
sockjs/routing.py                     116     15     30     10    83%
sockjs/session.py                     305      6    118     12    96%
sockjs/transports/__init__.py          10      0      0      0   100%
sockjs/transports/base.py             139     17     40      9    84%
sockjs/transports/eventsource.py       18      0      6      1    96%
sockjs/transports/htmlfile.py          34      0     10      1    98%
sockjs/transports/jsonp.py             50      0     16      0   100%
sockjs/transports/rawwebsocket.py      51      1     16      2    96%
sockjs/transports/utils.py             26      3      6      3    81%
sockjs/transports/websocket.py         63      2     14      1    96%
sockjs/transports/xhr.py               15      0      4      0   100%
sockjs/transports/xhrsend.py           29      0      8      0   100%
sockjs/transports/xhrstreaming.py      16      0      4      0   100%
---------------------------------------------------------------------
TOTAL                                 931     44    278     39    93%
```
