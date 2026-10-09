from rest_framework import parsers, viewsets, permissions, status
from rest_framework.decorators import api_view, permission_classes, authentication_classes, parser_classes
from rest_framework.authentication import BasicAuthentication, TokenAuthentication
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import (
    Vehicle,
    OfficeEquipment,
    EquipmentWorkOrder,
    EquipmentTransfer,
    Asset,
    AuditLog,
    DriverRequest,
    MaintenanceItem,
    StaffMember,
    CompanyDocument,
    OfficeEquipmentMaintenance,
)
from .permissions import get_user_role, is_admin, is_manager
from .serializers import (
    VehicleSerializer,
    OfficeEquipmentSerializer,
    AssetSerializer,
    StaffMemberSerializer,
    CompanyDocumentSerializer,
    OfficeEquipmentMaintenanceSerializer,
    EquipmentWorkOrderSerializer,
    VehicleMaintenanceSerializer,
    EquipmentTransferSerializer,
    DriverRequestSerializer,
    DriverAssignmentSerializer,
)
from . import views


class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.all().order_by('-updated_at')
    serializer_class = VehicleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [AdminWritePermission()]


class OfficeEquipmentViewSet(viewsets.ModelViewSet):
    queryset = OfficeEquipment.objects.all().order_by('-updated_at')
    serializer_class = OfficeEquipmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [AdminWritePermission()]


class AdminWritePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and is_admin(request.user))


class ManagerOrAdminPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and is_manager(request.user))


class EquipmentWorkOrderViewSet(viewsets.ModelViewSet):
    queryset = EquipmentWorkOrder.objects.select_related('equipment').all()
    serializer_class = EquipmentWorkOrderSerializer
    permission_classes = [ManagerOrAdminPermission]


class CompanyDocumentViewSet(viewsets.ModelViewSet):
    queryset = CompanyDocument.objects.all().order_by('expiry_date')
    serializer_class = CompanyDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [ManagerOrAdminPermission()]
        if self.action == 'create':
            return [AdminWritePermission()]
        return [ManagerOrAdminPermission()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


@api_view(['POST'])
@authentication_classes([TokenAuthentication, BasicAuthentication])
@permission_classes([permissions.AllowAny])
def get_token(request):
    """
    Get authentication token by providing username and password.
    Usage: POST /api/get-token/ with {"username": "user", "password": "pass"}
    Returns: {"token": "your-token-here"}
    """
    username = request.data.get('username')
    password = request.data.get('password')

    if not username or not password:
        return Response(
            {'error': 'username and password required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = None
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    if not user.check_password(password):
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    token, created = Token.objects.get_or_create(user=user)
    return Response({'token': str(token)})


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def staff_api(request):
    if not is_admin(request.user):
        return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    if request.method == 'GET':
        queryset = StaffMember.objects.all().order_by('staff_id')
        serializer = StaffMemberSerializer(queryset, many=True)
        return Response(serializer.data)

    serializer = StaffMemberSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def staff_detail_api(request, pk):
    if not is_admin(request.user):
        return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    staff = get_object_or_404(StaffMember, pk=pk)

    if request.method == 'GET':
        serializer = StaffMemberSerializer(staff)
        return Response(serializer.data)

    if request.method == 'PUT':
        serializer = StaffMemberSerializer(staff, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    staff.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def asset_detail_api(request, pk):
    if request.method != 'GET' and not is_admin(request.user):
        return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    asset = get_object_or_404(Asset, pk=pk)

    if request.method == 'GET':
        serializer = AssetSerializer(asset)
        return Response(serializer.data)

    if request.method == 'PUT':
        serializer = AssetSerializer(asset, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    asset.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def asset_assign_api(request, pk):
    if not is_admin(request.user):
        return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    asset = get_object_or_404(Asset, pk=pk)
    staff_id = request.data.get('staff_id') or request.data.get('staff_member_id') or request.data.get('assigned_staff_id')

    if not staff_id:
        return Response({'detail': 'staff_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    staff = get_object_or_404(StaffMember, pk=staff_id)
    asset.assigned_staff = staff
    asset.save(update_fields=['assigned_staff'])

    related_company_asset = getattr(asset, 'company_asset', None)
    if related_company_asset:
        related_company_asset.assigned_staff = staff
        related_company_asset.save(update_fields=['assigned_staff'])

    return Response({'detail': 'Asset assigned successfully', 'asset': AssetSerializer(asset).data})


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def asset_release_api(request, pk):
    if not is_admin(request.user):
        return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    asset = get_object_or_404(Asset, pk=pk)
    asset.assigned_staff = None
    asset.save(update_fields=['assigned_staff'])

    related_company_asset = getattr(asset, 'company_asset', None)
    if related_company_asset:
        related_company_asset.assigned_staff = None
        related_company_asset.save(update_fields=['assigned_staff'])

    return Response({'detail': 'Asset assignment released successfully', 'asset': AssetSerializer(asset).data})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def asset_history_api(request, pk):
    if not is_manager(request.user):
        return Response({'detail': 'Manager or admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    asset = get_object_or_404(Asset, pk=pk)
    history = []
    for entry in asset.assignments.all().order_by('-assigned_at'):
        history.append({
            'id': entry.pk,
            'staff_member': entry.staff_member.pk if entry.staff_member else None,
            'staff_name': str(entry.staff_member) if entry.staff_member else None,
            'assigned_at': entry.assigned_at.isoformat() if entry.assigned_at else None,
            'released_at': entry.released_at.isoformat() if entry.released_at else None,
            'is_active': entry.is_active,
        })
    return Response(history)


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser])
def documents_api(request):
    if request.method == 'GET' and not is_manager(request.user):
        return Response({'detail': 'Manager or admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    if request.method == 'POST' and not is_admin(request.user):
        return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    if request.method == 'GET':
        queryset = CompanyDocument.objects.all().order_by('-created_at')
        serializer = CompanyDocumentSerializer(queryset, many=True)
        return Response(serializer.data)

    serializer = CompanyDocumentSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def document_detail_api(request, pk):
    if not is_manager(request.user):
        return Response({'detail': 'Manager or admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    document = get_object_or_404(CompanyDocument, pk=pk)

    if request.method == 'GET':
        serializer = CompanyDocumentSerializer(document)
        return Response(serializer.data)

    if request.method in ['PUT', 'PATCH']:
        serializer = CompanyDocumentSerializer(document, data=request.data, partial=(request.method == 'PATCH'))
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    document.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def equipment_maintenance_api(request):
    if request.method != 'GET' and not is_manager(request.user):
        return Response({'detail': 'Manager or admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    if request.method == 'GET':
        queryset = OfficeEquipmentMaintenance.objects.all().order_by('-maintenance_date')
        serializer = OfficeEquipmentMaintenanceSerializer(queryset, many=True)
        return Response(serializer.data)

    serializer = OfficeEquipmentMaintenanceSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def equipment_maintenance_detail_api(request, pk):
    if request.method != 'GET' and not is_manager(request.user):
        return Response({'detail': 'Manager or admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    maintenance = get_object_or_404(OfficeEquipmentMaintenance, pk=pk)

    if request.method == 'GET':
        serializer = OfficeEquipmentMaintenanceSerializer(maintenance)
        return Response(serializer.data)

    if request.method in ['PUT', 'PATCH']:
        serializer = OfficeEquipmentMaintenanceSerializer(maintenance, data=request.data, partial=(request.method == 'PATCH'))
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    maintenance.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


def can_access_vehicle_maintenance(user, maintenance):
    if is_manager(user):
        return True
    staff_profile = getattr(user, 'staff_profile', None)
    return bool(staff_profile and maintenance.vehicle.assigned_staff_id == staff_profile.pk)


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def vehicle_maintenance_api(request):
    role = get_user_role(request.user)
    if role not in {'admin', 'manager', 'staff', 'driver'}:
        return Response({'detail': 'Access denied.'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        queryset = MaintenanceItem.objects.select_related('vehicle').order_by('-date_performed')
        if not is_manager(request.user):
            staff_profile = getattr(request.user, 'staff_profile', None)
            queryset = queryset.filter(vehicle__assigned_staff=staff_profile) if staff_profile else queryset.none()
        vehicle_id = request.query_params.get('vehicle')
        if vehicle_id:
            queryset = queryset.filter(vehicle_id=vehicle_id)
        return Response(VehicleMaintenanceSerializer(queryset, many=True).data)

    serializer = VehicleMaintenanceSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    vehicle = serializer.validated_data.get('vehicle')
    staff_profile = getattr(request.user, 'staff_profile', None)
    if not is_manager(request.user) and (not staff_profile or vehicle.assigned_staff_id != staff_profile.pk):
        return Response({'detail': 'You may only report maintenance for a vehicle assigned to you.'}, status=status.HTTP_403_FORBIDDEN)
    serializer.save()
    return Response(VehicleMaintenanceSerializer(serializer.instance).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def vehicle_maintenance_detail_api(request, pk):
    maintenance = get_object_or_404(MaintenanceItem.objects.select_related('vehicle'), pk=pk)
    if not can_access_vehicle_maintenance(request.user, maintenance):
        return Response({'detail': 'Access denied.'}, status=status.HTTP_403_FORBIDDEN)
    if request.method == 'GET':
        return Response(VehicleMaintenanceSerializer(maintenance).data)
    if not is_manager(request.user):
        return Response({'detail': 'Manager or admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    if request.method in {'PUT', 'PATCH'}:
        serializer = VehicleMaintenanceSerializer(
            maintenance,
            data=request.data,
            partial=request.method == 'PATCH',
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    maintenance.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def equipment_transfers_api(request):
    if request.method == 'GET':
        queryset = EquipmentTransfer.objects.select_related('equipment').all()
        equipment_id = request.query_params.get('equipment')
        if equipment_id:
            queryset = queryset.filter(equipment_id=equipment_id)
        return Response(EquipmentTransferSerializer(queryset, many=True).data)

    serializer = EquipmentTransferSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    equipment = serializer.validated_data['equipment']
    with transaction.atomic():
        transfer = serializer.save(
            transferred_from=equipment.assigned_user or 'Unassigned',
            recorded_by=request.user,
        )
        equipment.assigned_user = transfer.transferred_to
        equipment.save(update_fields=['assigned_user', 'updated_at'])
    return Response(EquipmentTransferSerializer(transfer).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def equipment_transfer_detail_api(request, pk):
    transfer = get_object_or_404(EquipmentTransfer.objects.select_related('equipment'), pk=pk)
    return Response(EquipmentTransferSerializer(transfer).data)


def can_view_driver_request(user, driver_request):
    if is_manager(user):
        return True
    staff_profile = getattr(user, 'staff_profile', None)
    return bool(
        driver_request.requester_user_id == user.pk
        or (staff_profile and driver_request.assigned_driver_id == staff_profile.pk)
    )


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def driver_requests_api(request):
    role = get_user_role(request.user)
    if role not in {'admin', 'manager', 'staff', 'driver'}:
        return Response({'detail': 'Access denied.'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        queryset = DriverRequest.objects.select_related('requested_by', 'requester_user', 'assigned_driver')
        if not is_manager(request.user):
            staff_profile = getattr(request.user, 'staff_profile', None)
            queryset = queryset.filter(
                Q(requester_user=request.user) | Q(assigned_driver=staff_profile)
            ) if staff_profile else queryset.filter(requester_user=request.user)
        if request.query_params.get('status'):
            queryset = queryset.filter(status=request.query_params['status'])
        return Response(DriverRequestSerializer(queryset, many=True).data)

    serializer = DriverRequestSerializer(data=request.data)
    if serializer.is_valid():
        driver_request = serializer.save(
            requester_user=request.user,
            requested_by=getattr(request.user, 'staff_profile', None),
        )
        AuditLog.objects.create(
            user=request.user,
            action='create',
            model_name='driverrequest',
            object_id=driver_request.pk,
            description='Created driver request',
        )
        return Response(DriverRequestSerializer(driver_request).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def driver_request_detail_api(request, pk):
    driver_request = get_object_or_404(
        DriverRequest.objects.select_related('requested_by', 'requester_user', 'assigned_driver'),
        pk=pk,
    )
    if not can_view_driver_request(request.user, driver_request):
        return Response({'detail': 'Access denied.'}, status=status.HTTP_403_FORBIDDEN)
    return Response(DriverRequestSerializer(driver_request).data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def driver_request_assign_api(request, pk):
    if not is_manager(request.user):
        return Response({'detail': 'Manager or admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    driver_request = get_object_or_404(DriverRequest, pk=pk)
    if driver_request.status == 'cancelled':
        return Response({'detail': 'Cannot assign a cancelled request.'}, status=status.HTTP_400_BAD_REQUEST)
    serializer = DriverAssignmentSerializer(data=request.data, instance=driver_request)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    assigned_driver = serializer.validated_data['assigned_driver']
    previous_driver = driver_request.assigned_driver
    if previous_driver and previous_driver.pk != assigned_driver.pk:
        previous_driver.driver_status = 'available'
        previous_driver.save(update_fields=['driver_status'])
    assigned_driver.driver_status = 'unavailable'
    assigned_driver.save(update_fields=['driver_status'])
    driver_request.assigned_driver = assigned_driver
    driver_request.assigned_by = request.user
    driver_request.assigned_at = timezone.now()
    driver_request.status = 'assigned'
    if 'notes' in serializer.validated_data:
        driver_request.notes = serializer.validated_data['notes']
    driver_request.save()
    AuditLog.objects.create(
        user=request.user,
        action='update',
        model_name='driverrequest',
        object_id=driver_request.pk,
        description=f'Assigned driver {assigned_driver} to request',
    )
    return Response(DriverRequestSerializer(driver_request).data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def me_api(request):
    return Response({
        'id': request.user.pk,
        'username': request.user.username,
        'email': request.user.email,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
        'role': get_user_role(request.user),
    })


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def password_reset_api(request):
    email = request.data.get('email', '').strip()
    if not email:
        return Response({'detail': 'email is required'}, status=status.HTTP_400_BAD_REQUEST)

    form = PasswordResetForm(data={'email': email})
    if form.is_valid():
        form.save(request=request, use_https=request.is_secure(), email_template_name='registration/password_reset_email.html')
        return Response({'detail': 'Password reset email sent if the account exists.'})

    return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def export_vehicles_csv_api(request):
    if not is_admin(request.user):
        return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    return views.export_vehicles_csv(request)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def export_equipment_csv_api(request):
    if not is_admin(request.user):
        return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    return views.export_equipment_csv(request)


@api_view(['POST'])
@authentication_classes([TokenAuthentication, BasicAuthentication])
@permission_classes([permissions.IsAuthenticated])
def bulk_upload_assets_api(request):
    if not is_admin(request.user):
        return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    return views.bulk_upload_assets.__wrapped__(request)


@api_view(['POST'])
@authentication_classes([TokenAuthentication, BasicAuthentication])
@permission_classes([permissions.IsAuthenticated])
def bulk_upload_equipment_api(request):
    if not is_admin(request.user):
        return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    return views.bulk_upload_equipment.__wrapped__(request)
