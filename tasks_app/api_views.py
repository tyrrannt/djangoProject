# tasks_app/api_views.py
from rest_framework import viewsets, permissions
from django.db.models import Q
from .models import Task, Category
from .serializers import TaskSerializer, CategorySerializer

class TaskViewSet(viewsets.ModelViewSet):
    """
    ViewSet for viewing and editing tasks.
    Users can see tasks they created or tasks shared with them.
    """
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Task.objects.filter(
            Q(user=user) | Q(shared_with=user)
        ).distinct().order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ReadOnly ViewSet for task categories.
    """
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]
