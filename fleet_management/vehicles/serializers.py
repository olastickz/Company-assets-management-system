from rest_framework import serializers
from .models import Vehicle, OfficeEquipment


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = '__all__'


class OfficeEquipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfficeEquipment
        fields = '__all__'
