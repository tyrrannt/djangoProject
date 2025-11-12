from rest_framework import serializers
from .models import DataBaseUser

class DataBaseUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataBaseUser
        fields = '__all__'  # или укажите конкретные поля