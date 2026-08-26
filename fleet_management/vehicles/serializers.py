from rest_framework import serializers
from .models import CompanyDocument, Vehicle, OfficeEquipment


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = '__all__'


class OfficeEquipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfficeEquipment
        fields = '__all__'


class CompanyDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyDocument
        fields = '__all__'
        read_only_fields = ['created_by', 'created_at', 'updated_at']
