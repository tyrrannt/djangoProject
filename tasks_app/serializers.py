"""Сериализаторы Django REST Framework для модуля tasks_app."""

from rest_framework import serializers

from customers_app.models import DataBaseUser
from tasks_app.models import (
    Category,
    SubTask,
    Task,
    TaskAssignment,
    TaskComment,
    TaskFile,
    TaskHistory,
)


class UserSerializer(serializers.ModelSerializer):
    """Упрощенный сериализатор пользователя для отображения участников задачи."""

    full_name = serializers.SerializerMethodField()

    class Meta:
        model = DataBaseUser
        fields = ['id', 'username', 'full_name', 'email']

    def get_full_name(self, obj: DataBaseUser) -> str:
        """Возвращает полное имя пользователя."""
        return obj.get_full_name() or getattr(obj, 'title', obj.username)


class CategorySerializer(serializers.ModelSerializer):
    """Сериализатор категорий задач."""

    class Meta:
        model = Category
        fields = ['id', 'name']


class TaskFileSerializer(serializers.ModelSerializer):
    """Сериализатор прикрепленных файлов."""

    uploaded_by = UserSerializer(read_only=True)

    class Meta:
        model = TaskFile
        fields = ['id', 'file', 'original_filename', 'file_size', 'description', 'uploaded_by', 'uploaded_at']


class SubTaskSerializer(serializers.ModelSerializer):
    """Сериализатор подзадач / чек-листа."""

    assigned_to = UserSerializer(read_only=True)
    completed_by = UserSerializer(read_only=True)

    class Meta:
        model = SubTask
        fields = ['id', 'title', 'is_completed', 'assigned_to', 'completed_by', 'completed_at', 'order', 'created_at']


class TaskCommentSerializer(serializers.ModelSerializer):
    """Сериализатор комментариев."""

    author = UserSerializer(read_only=True)

    class Meta:
        model = TaskComment
        fields = ['id', 'author', 'parent', 'text', 'created_at', 'updated_at']


class TaskHistorySerializer(serializers.ModelSerializer):
    """Сериализатор записей аудита истории задачи."""

    user = UserSerializer(read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = TaskHistory
        fields = ['id', 'user', 'action', 'action_display', 'old_value', 'new_value', 'comment', 'created_at']


class TaskAssignmentSerializer(serializers.ModelSerializer):
    """Сериализатор поручений и делегирования."""

    assigned_by = UserSerializer(read_only=True)
    assigned_to = UserSerializer(read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = TaskAssignment
        fields = [
            'id', 'assigned_by', 'assigned_to', 'role', 'role_display',
            'status', 'status_display', 'comment', 'assigned_at', 'accepted_at', 'completed_at'
        ]


class TaskSerializer(serializers.ModelSerializer):
    """Основной комплексный сериализатор задачи."""

    user = UserSerializer(read_only=True)
    responsible = UserSerializer(read_only=True)
    responsible_id = serializers.PrimaryKeyRelatedField(
        queryset=DataBaseUser.objects.all(), source='responsible', write_only=True, required=False, allow_null=True
    )
    assignees = UserSerializer(many=True, read_only=True)
    assignees_ids = serializers.PrimaryKeyRelatedField(
        queryset=DataBaseUser.objects.all(), source='assignees', many=True, write_only=True, required=False
    )
    observers = UserSerializer(many=True, read_only=True)
    observers_ids = serializers.PrimaryKeyRelatedField(
        queryset=DataBaseUser.objects.all(), source='observers', many=True, write_only=True, required=False
    )
    shared_with = UserSerializer(many=True, read_only=True)
    shared_with_ids = serializers.PrimaryKeyRelatedField(
        queryset=DataBaseUser.objects.all(), source='shared_with', many=True, write_only=True, required=False
    )
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True, required=False, allow_null=True
    )
    files = TaskFileSerializer(many=True, read_only=True)
    subtasks = SubTaskSerializer(many=True, read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    repeat_rule_display = serializers.CharField(source='get_repeat_rule_display', read_only=True)

    class Meta:
        model = Task
        fields = [
            'id', 'user', 'responsible', 'responsible_id', 'assignees', 'assignees_ids',
            'observers', 'observers_ids', 'shared_with', 'shared_with_ids', 'title', 'description',
            'status', 'status_display', 'completed', 'priority', 'priority_display',
            'category', 'category_id', 'start_date', 'end_date', 'accepted_at', 'submitted_review_at',
            'completed_at', 'requires_eds', 'progress_percent', 'is_overdue',
            'repeat', 'repeat_interval', 'repeat_days', 'repeat_end_date', 'repeat_rule_display',
            'files', 'subtasks', 'created_at'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at', 'completed_at', 'repeat_rule_display']

    def create(self, validated_data):
        assignees = validated_data.pop('assignees', [])
        observers = validated_data.pop('observers', [])
        shared_with = validated_data.pop('shared_with', [])

        task = Task.objects.create(**validated_data)
        if assignees:
            task.assignees.set(assignees)
        if observers:
            task.observers.set(observers)
        if shared_with:
            task.shared_with.set(shared_with)
        return task


class TaskDelegationSerializer(serializers.Serializer):
    """Сериализатор параметров делегирования задачи."""

    assigned_to_id = serializers.IntegerField(required=True)
    role = serializers.CharField(required=False, default='assignee')
    comment = serializers.CharField(required=False, allow_blank=True, default='')


class DisciplineReportSummarySerializer(serializers.Serializer):
    """Сериализатор сводных показателей отчета по исполнительской дисциплине."""

    total_count = serializers.IntegerField()
    completed_on_time_count = serializers.IntegerField()
    completed_overdue_count = serializers.IntegerField()
    in_progress_count = serializers.IntegerField()
    active_overdue_count = serializers.IntegerField()
    eds_signed_count = serializers.IntegerField()
    discipline_rate = serializers.FloatField()
    avg_completion_days = serializers.FloatField()
