# sockjs-channels

`sockjs-channels` is a [SockJS](http://sockjs.org) integration for [Django Channels](https://github.com/django/channels/), some features are referenced from [sockjs-aiohttp](https://github.com/aio-libs/sockjs/). sockjs-channels interface
is implemented as a ASGI routing, it runs inside a ASGI application rather than ASGI server. Its possible to create any number of different sockjs routings, ie `/sockjs/*` or `/chat-sockjs/*`. You can provide different session implementation and management for each sockjs routing.

## Requirements
* Python 3.6+
* Django 3.2+
* Channels 3.0.0+

## Installation
```bash
$ pip install sockjs-channels
```

## ASGI routing
Here’s an example of `asgi.py` might look like:
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
        *routing.http,
    ]),
    'websocket': URLRouter([
        *routing.websocket
    ]),
})
```


## Supported transports
* websocket
* xhr-streaming
* xhr-polling
* iframe-xhr-polling
* iframe-eventsource
* iframe-htmlfile
* jsonp-polling

## Examples
You can find a simple chat example in the sockjs-channels repository at github.

[https://github.com/iTraceur/sockjs-channels/tree/master/examples](https://github.com/iTraceur/sockjs-channels/tree/master/examples)

## License
sockjs-channels is offered under the MIT license.

## Test Coverage
```
Name                                Stmts   Miss Branch BrPart  Cover
---------------------------------------------------------------------
sockjs/routing.py                     116     15     30     10    83%
sockjs/session.py                     305      6    118     13    96%
sockjs/transports/base.py             137     19     38      8    83%
sockjs/transports/eventsource.py       22      0      6      1    96%
sockjs/transports/htmlfile.py          39      0     10      1    98%
sockjs/transports/rawwebsocket.py      50     19     18      5    56%
sockjs/transports/utils.py             26      3      6      3    81%
sockjs/transports/websocket.py         62     29     16      3    51%
---------------------------------------------------------------------
TOTAL                                 942     91    280     44    88%
```