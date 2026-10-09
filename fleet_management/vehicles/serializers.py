from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Asset,
    CompanyDocument,
    DriverRequest,
    EquipmentTransfer,
    EmailRecipient,
    EquipmentWorkOrder,
    MaintenanceItem,
    OfficeEquipment,
    OfficeEquipmentMaintenance,
    StaffMember,
    UserRole,
    Vehicle,
)


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


class VehicleMaintenanceSerializer(serializers.ModelSerializer):
    vehicle_name = serializers.CharField(source='vehicle.name', read_only=True)

    class Meta:
        model = MaintenanceItem
        fields = ['id', 'vehicle', 'vehicle_name', 'description', 'date_performed', 'cost', 'notes']


class EquipmentTransferSerializer(serializers.ModelSerializer):
    equipment_name = serializers.CharField(source='equipment.name', read_only=True)

    class Meta:
        model = EquipmentTransfer
        fields = [
            'id', 'equipment', 'equipment_name', 'transferred_from',
            'transferred_from_department', 'transferred_from_email',
            'transferred_to', 'transferred_to_department', 'transferred_to_email',
            'transfer_date', 'reason', 'notes', 'recorded_by', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'equipment_name', 'transferred_from', 'transfer_date', 'recorded_by',
            'created_at', 'updated_at',
        ]


class DriverRequestSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.CharField(source='requested_by.full_name', read_only=True)
    assigned_driver_name = serializers.CharField(source='assigned_driver.full_name', read_only=True)

    class Meta:
        model = DriverRequest
        fields = [
            'id', 'requested_by', 'requested_by_name', 'requester_user', 'details',
            'preferred_date', 'status', 'assigned_driver', 'assigned_driver_name',
            'assigned_by', 'assigned_at', 'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'requested_by', 'requested_by_name', 'requester_user', 'status',
            'assigned_driver', 'assigned_driver_name', 'assigned_by', 'assigned_at',
            'created_at', 'updated_at',
        ]


class DriverAssignmentSerializer(serializers.Serializer):
    assigned_driver = serializers.PrimaryKeyRelatedField(queryset=StaffMember.objects.none())
    notes = serializers.CharField(required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        drivers = StaffMember.objects.filter(
            user__role__role='driver',
            driver_status='available',
            is_active=True,
        )
        instance = kwargs.get('instance')
        if instance and instance.assigned_driver_id:
            drivers = drivers | StaffMember.objects.filter(pk=instance.assigned_driver_id)
        self.fields['assigned_driver'].queryset = drivers.distinct()


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


class AdminUserSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=UserRole.ROLE_CHOICES, required=False, write_only=True)
    department = serializers.CharField(max_length=100, allow_blank=True, allow_null=True, required=False, write_only=True)
    is_superuser = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 'is_active',
            'is_superuser', 'role', 'department',
        ]
        read_only_fields = ['id', 'is_superuser']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        try:
            data['role'] = instance.role.role
            data['department'] = instance.role.department
        except UserRole.DoesNotExist:
            data['role'] = 'admin' if instance.is_superuser else 'staff'
            data['department'] = None
        return data

    def create(self, validated_data):
        role = validated_data.pop('role', 'staff')
        department = validated_data.pop('department', None)
        user = User(**validated_data)
        user.set_unusable_password()
        user.save()
        UserRole.objects.create(user=user, role=role, department=department)
        return user

    def update(self, instance, validated_data):
        role = validated_data.pop('role', None)
        department_was_provided = 'department' in validated_data
        department = validated_data.pop('department', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if validated_data:
            instance.save()
        if role is not None or department_was_provided:
            user_role, _ = UserRole.objects.get_or_create(user=instance, defaults={'role': 'staff'})
            if role is not None:
                user_role.role = role
            if department_was_provided:
                user_role.department = department
            user_role.save()
        return instance


class NotificationRecipientSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailRecipient
        fields = ['id', 'email', 'full_name', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']
