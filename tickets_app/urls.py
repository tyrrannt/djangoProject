from django.urls import path
from .views import (
    TicketListView,
    TicketDetailView,
    TicketCreateView,
    TicketUpdateView,
    add_message_to_ticket,
)

app_name = 'tickets_app'

urlpatterns = [
    path('', TicketListView.as_view(), name='list'),
    path('create/', TicketCreateView.as_view(), name='create'),
    path('<int:pk>/', TicketDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', TicketUpdateView.as_view(), name='edit'),
    path('<int:pk>/message/', add_message_to_ticket, name='add_message'),
]