"""
ASGI config for chat project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import re_path

from sockjs import make_routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chat.settings')

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

from .views import chat_msg_handler

routing = make_routing(chat_msg_handler, name='chat')

# Add django's url router
routing.http.append(re_path(r'', django_asgi_app))

application = ProtocolTypeRouter({
    'http': URLRouter([
        *routing.http
    ]),
    'websocket': URLRouter([
        *routing.websocket
    ])
})
