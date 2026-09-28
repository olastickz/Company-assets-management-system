from rest_framework import serializers
from .models import Vehicle, OfficeEquipment, EquipmentWorkOrder, Asset, StaffMember, CompanyDocument, OfficeEquipmentMaintenance


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
        read_only_fields = ['created_by', 'created_at', 'updated_at']


class OfficeEquipmentMaintenanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfficeEquipmentMaintenance
        fields = '__all__'


class EquipmentWorkOrderSerializer(serializers.ModelSerializer):
    machine_name = serializers.CharField(source='equipment.name', read_only=True)
    equipment_type = serializers.CharField(source='equipment.equipment_type', read_only=True)
    office_location = serializers.CharField(source='equipment.regional_office', read_only=True)
    report_name = serializers.CharField(source='title', read_only=True)

    class Meta:
        model = EquipmentWorkOrder
        fields = [
            'id',
            'equipment',
            'machine_name',
            'equipment_type',
            'office_location',
            'work_type',
            'title',
            'report_name',
            'description',
            'priority',
            'status',
            'due_date',
            'created_at',
            'updated_at',
            'completed_at',
        ]
        read_only_fields = ['created_at', 'updated_at', 'completed_at']
