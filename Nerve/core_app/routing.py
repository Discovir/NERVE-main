from django.urls import path
from core_app.consumers.emg_consumer import EMGConsumer

websocket_urlpatterns = [
    path("ws/emg/", EMGConsumer.as_asgi()),
]
