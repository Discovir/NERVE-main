import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Nerve.settings")
django.setup()

from core_app.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        # Standard HTTP — Django Ninja REST endpoints live here
        "http": get_asgi_application(),
        # WebSocket — live EMG stream
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)