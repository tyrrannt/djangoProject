from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import ChatViewSet

router = DefaultRouter()
router.register(r'chats', ChatViewSet, basename='api_chat')

urlpatterns = [
    path('', include(router.urls)),
]
