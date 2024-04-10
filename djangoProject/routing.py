# routing.py

from django.urls import path

from customers_app import consumers

websocket_urlpatterns = [
    path(r'ws/echo/', consumers.EchoConsumer.as_asgi()),
]