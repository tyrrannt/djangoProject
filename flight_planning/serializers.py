# flight_planning/serializers.py
from rest_framework import serializers
from .models import PilotAssignment
from hrdepartment_app.models import PlaceProductionActivity
from customers_app.models import DataBaseUser

class PilotSerializer(serializers.ModelSerializer):
    """
    Serializer for the DataBaseUser model (simplified for pilot info).
    """
    full_name = serializers.CharField(source='title', read_only=True)

    class Meta:
        model = DataBaseUser
        fields = ['id', 'username', 'full_name']

class MPDSerializer(serializers.ModelSerializer):
    """
    Serializer for the PlaceProductionActivity model.
    """
    class Meta:
        model = PlaceProductionActivity
        fields = ['id', 'name', 'short_name']

class PilotAssignmentSerializer(serializers.ModelSerializer):
    """
    Serializer for the PilotAssignment model.
    """
    pilot = PilotSerializer(read_only=True)
    mpd = MPDSerializer(read_only=True)

    class Meta:
        model = PilotAssignment
        fields = ['id', 'pilot', 'mpd', 'date', 'created_at']

class GroupedScheduleSerializer(serializers.Serializer):
    """
    Serializer for grouped schedule ranges.
    """
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    mpd_name = serializers.CharField()
    is_gap = serializers.BooleanField()
    days_count = serializers.IntegerField()
