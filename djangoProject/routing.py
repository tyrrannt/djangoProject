# routing.py

from django.urls import path

from customers_app import consumers

websocket_urlpatterns = [
    path(r'ws/online_users/', consumers.OnlineUsersConsumer.as_asgi()),
    path('ws/chat/<str:room_name>/', consumers.ChatConsumer.as_asgi()),
    path('ws/monitor/', consumers.MonitorConsumer.as_asgi()),
    path('ws/video_conference/<str:room_name>/', consumers.VideoConferenceConsumer.as_asgi()),
]