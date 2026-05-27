# tasks_app/serializers.py
from rest_framework import serializers
from .models import Task, Category, TaskFile
from customers_app.models import DataBaseUser

class UserSerializer(serializers.ModelSerializer):
    """
    Simplified user serializer for task associations.
    """
    full_name = serializers.CharField(source='title', read_only=True)

    class Meta:
        model = DataBaseUser
        fields = ['id', 'username', 'full_name']

class CategorySerializer(serializers.ModelSerializer):
    """
    Serializer for Task categories.
    """
    class Meta:
        model = Category
        fields = ['id', 'name']

class TaskFileSerializer(serializers.ModelSerializer):
    """
    Serializer for files attached to tasks.
    """
    class Meta:
        model = TaskFile
        fields = ['id', 'file', 'original_filename', 'uploaded_at']

class TaskSerializer(serializers.ModelSerializer):
    """
    Comprehensive serializer for Tasks.
    """
    user = UserSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True, required=False, allow_null=True
    )
    files = TaskFileSerializer(many=True, read_only=True)
    shared_with = UserSerializer(many=True, read_only=True)
    shared_with_ids = serializers.PrimaryKeyRelatedField(
        queryset=DataBaseUser.objects.all(), source='shared_with', many=True, write_only=True, required=False
    )

    class Meta:
        model = Task
        fields = [
            'id', 'user', 'shared_with', 'shared_with_ids', 'title', 'description', 
            'completed', 'created_at', 'start_date', 'end_date', 'priority', 
            'category', 'category_id', 'repeat', 'files'
        ]
        read_only_fields = ['user', 'created_at']

    def create(self, validated_data):
        shared_with = validated_data.pop('shared_with', [])
        task = Task.objects.create(**validated_data)
        if shared_with:
            task.shared_with.set(shared_with)
        return task
