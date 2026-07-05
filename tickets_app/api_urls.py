from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import TicketViewSet

router = DefaultRouter()
router.register(r'tickets', TicketViewSet, basename='api_ticket')

urlpatterns = [
    path('', include(router.urls)),
]
