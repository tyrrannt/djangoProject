# flight_planning/serializers.py
from rest_framework import serializers
from .models import PilotAssignment, AircraftMovement
from hrdepartment_app.models import PlaceProductionActivity
from customers_app.models import DataBaseUser
from contracts_app.models import Estate


class AircraftSerializer(serializers.ModelSerializer):
    """
    Serializer for the Estate model (aircraft).
    """
    type_name = serializers.CharField(source='type_property.type_property', read_only=True)
    is_decommissioned = serializers.BooleanField(read_only=True)

    class Meta:
        model = Estate
        fields = [
            'id',
            'registration_number',
            'factory_number',
            'type_property',
            'type_name',
            'release_date',
            'decommission_date',
            'is_decommissioned'
        ]


class MPDSerializer(serializers.ModelSerializer):
    """
    Serializer for the PlaceProductionActivity model.
    """

    class Meta:
        model = PlaceProductionActivity
        fields = ['id', 'name', 'short_name']


class AircraftMovementSerializer(serializers.ModelSerializer):
    """
    Serializer for the AircraftMovement model.
    """
    aircraft = AircraftSerializer(read_only=True)
    aircraft_id = serializers.PrimaryKeyRelatedField(
        queryset=Estate.objects.all(),
        source='aircraft',
        write_only=True
    )
    mpd = MPDSerializer(read_only=True)
    mpd_id = serializers.PrimaryKeyRelatedField(
        queryset=PlaceProductionActivity.objects.all(),
        source='mpd',
        write_only=True
    )

    class Meta:
        model = AircraftMovement
        fields = [
            'id',
            'aircraft',
            'aircraft_id',
            'mpd',
            'mpd_id',
            'date',
            'comment',
            'created_at',
            'created_by'
        ]


class PilotSerializer(serializers.ModelSerializer):
    """
    Serializer for the DataBaseUser model (simplified for pilot info).
    """
    full_name = serializers.CharField(source='title', read_only=True)

    class Meta:
        model = DataBaseUser
        fields = ['id', 'username', 'full_name']


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
    crew = serializers.ListField(child=serializers.CharField())
