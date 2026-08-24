from rest_framework import serializers
from .models import Vehicle, OfficeEquipment, Asset, StaffMember, CompanyDocument, OfficeEquipmentMaintenance


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = '__all__'


class OfficeEquipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfficeEquipment
        fields = '__all__'


class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = '__all__'


class StaffMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffMember
        fields = '__all__'


class CompanyDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyDocument
        fields = '__all__'


class OfficeEquipmentMaintenanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfficeEquipmentMaintenance
        fields = '__all__'
