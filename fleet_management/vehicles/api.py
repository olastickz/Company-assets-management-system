import logging

from django.conf import settings
from rest_framework import parsers, viewsets, permissions, status
from rest_framework.decorators import api_view, permission_classes, authentication_classes, parser_classes
from rest_framework.authentication import BasicAuthentication, TokenAuthentication
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError as APIValidationError
from rest_framework.authtoken.models import Token
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
    AssetAssignmentRequest,
    MaintenanceItem,
    MaintenanceRequest,
    StaffMember,
    CompanyDocument,
    OfficeEquipmentMaintenance,
)
from .asset_assignment_workflow import (
    AssignmentWorkflowError,
    approve_assignment_request,
    reject_assignment_request,
    submit_assignment_request,
)
from .permissions import RoleMatrixPermission, get_user_role, has_role_permission, is_admin, is_manager
from .serializers import (
    VehicleSerializer,
    OfficeEquipmentSerializer,
    AssetSerializer,
    StaffMemberSerializer,
    CompanyDocumentSerializer,
    OfficeEquipmentMaintenanceSerializer,
    EquipmentWorkOrderSerializer,
    VehicleMaintenanceSerializer,
    MaintenanceRequestSerializer,
    EquipmentTransferSerializer,
    DriverRequestSerializer,
    DriverAssignmentSerializer,
    AssetAssignmentRequestSerializer,
)
from . import views

logger = logging.getLogger(__name__)


class AssignmentRequestResponseMixin:
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        self.assignment_request = None
        response = super().create(request, *args, **kwargs)
        if self.assignment_request:
            response.data = {
                'detail': 'Resource created; assignment request is pending approval.',
                'request_id': self.assignment_request.pk,
                'resource': response.data,
            }
            response.status_code = status.HTTP_202_ACCEPTED
        return response

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        self.assignment_request = None
        response = super().update(request, *args, **kwargs)
        if self.assignment_request:
            response.data = {
                'detail': 'Resource updated; assignment request is pending approval.',
                'request_id': self.assignment_request.pk,
                'resource': response.data,
            }
            response.status_code = status.HTTP_202_ACCEPTED
        return response


class VehicleViewSet(AssignmentRequestResponseMixin, viewsets.ModelViewSet):
    queryset = Vehicle.objects.all().order_by('-updated_at')
    serializer_class = VehicleSerializer
    permission_classes = [RoleMatrixPermission]
    permission_module = 'vehicles'

    def perform_create(self, serializer):
        requested_staff = serializer.validated_data.pop('assigned_staff', None)
        record = serializer.save(assigned_staff=None)
        if requested_staff:
            try:
                self.assignment_request = submit_assignment_request(record.asset, requested_staff, self.request.user)
            except AssignmentWorkflowError as error:
                raise APIValidationError({'assigned_staff': str(error)})

    def perform_update(self, serializer):
        requested_staff = serializer.validated_data.pop('assigned_staff', serializer.instance.assigned_staff)
        previous_staff = serializer.instance.assigned_staff
        record = serializer.save(assigned_staff=previous_staff)
        if requested_staff and requested_staff.pk != getattr(previous_staff, 'pk', None):
            try:
                self.assignment_request = submit_assignment_request(record.asset, requested_staff, self.request.user)
            except AssignmentWorkflowError as error:
                raise APIValidationError({'assigned_staff': str(error)})


class OfficeEquipmentViewSet(AssignmentRequestResponseMixin, viewsets.ModelViewSet):
    queryset = OfficeEquipment.objects.all().order_by('-updated_at')
    serializer_class = OfficeEquipmentSerializer
    permission_classes = [RoleMatrixPermission]
    permission_module = 'equipment'

    def perform_create(self, serializer):
        requested_staff = serializer.validated_data.pop('assigned_staff', None)
        record = serializer.save(assigned_staff=None)
        if requested_staff:
            try:
                self.assignment_request = submit_assignment_request(record.asset, requested_staff, self.request.user)
            except AssignmentWorkflowError as error:
                raise APIValidationError({'assigned_staff': str(error)})

    def perform_update(self, serializer):
        requested_staff = serializer.validated_data.pop('assigned_staff', serializer.instance.assigned_staff)
        previous_staff = serializer.instance.assigned_staff
        record = serializer.save(assigned_staff=previous_staff)
        if requested_staff and requested_staff.pk != getattr(previous_staff, 'pk', None):
            try:
                self.assignment_request = submit_assignment_request(record.asset, requested_staff, self.request.user)
            except AssignmentWorkflowError as error:
                raise APIValidationError({'assigned_staff': str(error)})


class EquipmentWorkOrderViewSet(viewsets.ModelViewSet):
    queryset = EquipmentWorkOrder.objects.select_related('equipment').all()
    serializer_class = EquipmentWorkOrderSerializer
    permission_classes = [RoleMatrixPermission]
    permission_module = 'work_orders'


class CompanyDocumentViewSet(viewsets.ModelViewSet):
    queryset = CompanyDocument.objects.all().order_by('expiry_date')
    serializer_class = CompanyDocumentSerializer
    permission_classes = [RoleMatrixPermission]
    permission_module = 'documents'
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

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
@permission_classes([RoleMatrixPermission.for_module('staff')])
def staff_api(request):
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
@permission_classes([RoleMatrixPermission.for_module('staff')])
def staff_detail_api(request, pk):
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
@permission_classes([RoleMatrixPermission.for_module('vehicles')])
def asset_detail_api(request, pk):
    asset = get_object_or_404(Asset, pk=pk)

    if request.method == 'GET':
        serializer = AssetSerializer(asset)
        return Response(serializer.data)

    if request.method == 'PUT':
        payload = request.data.copy()
        requested_staff_id = payload.get('assigned_staff')
        payload.pop('assigned_staff', None)
        payload.pop('assigned_staff_id', None)
        serializer = AssetSerializer(asset, data=payload, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        assignment_request = None
        if requested_staff_id not in (None, ''):
            if isinstance(requested_staff_id, (list, tuple)):
                requested_staff_id = requested_staff_id[-1] if requested_staff_id else None
            try:
                staff_member = StaffMember.objects.get(pk=requested_staff_id, is_active=True)
                assignment_request = submit_assignment_request(asset, staff_member, request.user)
            except StaffMember.DoesNotExist:
                return Response({'detail': 'Selected staff member was not found or is inactive.'}, status=status.HTTP_400_BAD_REQUEST)
            except AssignmentWorkflowError as error:
                return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)
            if assignment_request is None:
                return Response({'detail': 'Asset is already assigned to this staff member.', 'asset': AssetSerializer(asset).data})
        serializer.save()
        if assignment_request:
            return Response({
                'detail': 'Assignment request submitted for approval.',
                'request_id': assignment_request.pk,
                'asset': serializer.data,
            }, status=status.HTTP_202_ACCEPTED)
        return Response(serializer.data)

    asset.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([RoleMatrixPermission.for_module('vehicles', {'POST': 'edit'})])
def asset_assign_api(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    staff_id = request.data.get('staff_id') or request.data.get('staff_member_id') or request.data.get('assigned_staff_id')

    if not staff_id:
        return Response({'detail': 'staff_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    staff = get_object_or_404(StaffMember, pk=staff_id, is_active=True)
    try:
        assignment = submit_assignment_request(asset, staff, request.user)
    except AssignmentWorkflowError as error:
        return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)
    if assignment is None:
        return Response({'detail': 'Asset is already assigned to this staff member.', 'asset': AssetSerializer(asset).data})
    return Response(
        {'detail': 'Assignment request submitted for approval.', 'request_id': assignment.pk},
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def asset_assignment_request_api(request, pk):
    assignment = get_object_or_404(
        AssetAssignmentRequest.objects.select_related(
            'asset', 'previous_staff', 'requested_staff', 'requested_by',
            'supervisor_approver', 'supervisor_approved_by',
            'reporting_manager_approver', 'reporting_manager_approved_by',
            'superadmin_approved_by',
        ),
        pk=pk,
    )
    allowed_users = {
        assignment.supervisor_approver_id,
        assignment.reporting_manager_approver_id,
        assignment.requested_by_id,
    }
    if not is_admin(request.user) and request.user.pk not in allowed_users:
        return Response({'detail': 'You cannot view this assignment request.'}, status=status.HTTP_403_FORBIDDEN)
    return Response(AssetAssignmentRequestSerializer(assignment).data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def asset_assignment_request_approve_api(request, pk):
    try:
        assignment = approve_assignment_request(pk, request.user)
    except AssetAssignmentRequest.DoesNotExist:
        return Response({'detail': 'Assignment request not found.'}, status=status.HTTP_404_NOT_FOUND)
    except PermissionError as error:
        return Response({'detail': str(error)}, status=status.HTTP_403_FORBIDDEN)
    except AssignmentWorkflowError as error:
        return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(AssetAssignmentRequestSerializer(assignment).data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def asset_assignment_request_reject_api(request, pk):
    try:
        assignment = reject_assignment_request(
            pk, request.user, request.data.get('rejection_note', '').strip()
        )
    except AssetAssignmentRequest.DoesNotExist:
        return Response({'detail': 'Assignment request not found.'}, status=status.HTTP_404_NOT_FOUND)
    except PermissionError as error:
        return Response({'detail': str(error)}, status=status.HTTP_403_FORBIDDEN)
    except AssignmentWorkflowError as error:
        return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(AssetAssignmentRequestSerializer(assignment).data)


@api_view(['POST'])
@permission_classes([RoleMatrixPermission.for_module('vehicles', {'POST': 'edit'})])
def asset_release_api(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    asset.assigned_staff = None
    asset.save(update_fields=['assigned_staff'])

    related_company_asset = getattr(asset, 'company_asset', None)
    if related_company_asset:
        related_company_asset.assigned_staff = None
        related_company_asset.save(update_fields=['assigned_staff'])

    return Response({'detail': 'Asset assignment released successfully', 'asset': AssetSerializer(asset).data})


@api_view(['GET'])
@permission_classes([RoleMatrixPermission.for_module('vehicles')])
def asset_history_api(request, pk):
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
@permission_classes([RoleMatrixPermission.for_module('documents')])
@parser_classes([parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser])
def documents_api(request):
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
@permission_classes([RoleMatrixPermission.for_module('documents')])
def document_detail_api(request, pk):
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
@permission_classes([RoleMatrixPermission.for_module('equipment_maintenance')])
def equipment_maintenance_api(request):
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
@permission_classes([RoleMatrixPermission.for_module('equipment_maintenance')])
def equipment_maintenance_detail_api(request, pk):
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


@api_view(['GET'])
@permission_classes([RoleMatrixPermission.for_module('maintenance')])
def maintenance_due_api(request):
    if not is_admin(request.user):
        return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)

    today = timezone.localdate()
    due_assets = []
    asset_sources = (
        ('vehicle', Vehicle.objects.exclude(maintenance_due_date__isnull=True)),
        ('equipment', OfficeEquipment.objects.exclude(maintenance_due_date__isnull=True)),
    )
    for asset_type, assets in asset_sources:
        for asset in assets.only('pk', 'name', 'maintenance_due_date'):
            due_assets.append({
                'asset_id': asset.pk,
                'asset_type': asset_type,
                'asset_name': asset.name,
                'maintenance_due_date': asset.maintenance_due_date,
                'status': 'overdue' if asset.maintenance_due_date < today else 'upcoming',
            })

    due_assets.sort(key=lambda item: item['maintenance_due_date'])
    return Response({'count': len(due_assets), 'results': due_assets})


@api_view(['GET', 'POST'])
@permission_classes([RoleMatrixPermission.for_module('requests')])
@parser_classes([parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser])
def maintenance_requests_api(request):
    role = get_user_role(request.user)

    if request.method == 'POST':
        if role not in {'staff', 'driver'}:
            return Response({'detail': 'Only staff and drivers can submit maintenance requests.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = MaintenanceRequestSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save(submitted_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if not is_admin(request.user):
        return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    requests = MaintenanceRequest.objects.select_related('submitted_by').all()
    return Response(MaintenanceRequestSerializer(requests, many=True, context={'request': request}).data)


def can_access_vehicle_maintenance(user, maintenance):
    if has_role_permission(user, 'vehicle_maintenance', 'view'):
        return True
    staff_profile = getattr(user, 'staff_profile', None)
    return bool(staff_profile and maintenance.vehicle.assigned_staff_id == staff_profile.pk)


@api_view(['GET', 'POST'])
@permission_classes([RoleMatrixPermission.for_module('vehicle_maintenance')])
def vehicle_maintenance_api(request):
    if request.method == 'GET':
        queryset = MaintenanceItem.objects.select_related('vehicle').order_by('-date_performed')
        if not has_role_permission(request.user, 'vehicle_maintenance', 'view'):
            staff_profile = getattr(request.user, 'staff_profile', None)
            queryset = queryset.filter(vehicle__assigned_staff=staff_profile) if staff_profile else queryset.none()
        vehicle_id = request.query_params.get('vehicle')
        if vehicle_id:
            queryset = queryset.filter(vehicle_id=vehicle_id)
        return Response(VehicleMaintenanceSerializer(queryset, many=True).data)

    serializer = VehicleMaintenanceSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    serializer.save()
    return Response(VehicleMaintenanceSerializer(serializer.instance).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([RoleMatrixPermission.for_module('vehicle_maintenance')])
def vehicle_maintenance_detail_api(request, pk):
    maintenance = get_object_or_404(MaintenanceItem.objects.select_related('vehicle'), pk=pk)
    if not can_access_vehicle_maintenance(request.user, maintenance):
        return Response({'detail': 'Access denied.'}, status=status.HTTP_403_FORBIDDEN)
    if request.method == 'GET':
        return Response(VehicleMaintenanceSerializer(maintenance).data)
    if not has_role_permission(request.user, 'vehicle_maintenance', 'edit'):
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
@permission_classes([RoleMatrixPermission.for_module('transfers')])
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
@permission_classes([RoleMatrixPermission.for_module('transfers')])
def equipment_transfer_detail_api(request, pk):
    transfer = get_object_or_404(EquipmentTransfer.objects.select_related('equipment'), pk=pk)
    return Response(EquipmentTransferSerializer(transfer).data)


def can_view_driver_request(user, driver_request):
    if is_admin(user) or get_user_role(user) == 'vehicle_manager':
        return True
    staff_profile = getattr(user, 'staff_profile', None)
    return bool(
        driver_request.requester_user_id == user.pk
        or (staff_profile and driver_request.assigned_driver_id == staff_profile.pk)
    )


@api_view(['GET', 'POST'])
@permission_classes([RoleMatrixPermission.for_module('requests')])
def driver_requests_api(request):
    if request.method == 'GET':
        queryset = DriverRequest.objects.select_related('requested_by', 'requester_user', 'assigned_driver')
        if not (is_admin(request.user) or get_user_role(request.user) == 'vehicle_manager'):
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
@permission_classes([RoleMatrixPermission.for_module('requests')])
def driver_request_detail_api(request, pk):
    driver_request = get_object_or_404(
        DriverRequest.objects.select_related('requested_by', 'requester_user', 'assigned_driver'),
        pk=pk,
    )
    if not can_view_driver_request(request.user, driver_request):
        return Response({'detail': 'Access denied.'}, status=status.HTTP_403_FORBIDDEN)
    return Response(DriverRequestSerializer(driver_request).data)


@api_view(['POST'])
@permission_classes([RoleMatrixPermission.for_module('requests', {'POST': ('approve', 'level_1')})])
def driver_request_assign_api(request, pk):
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


@api_view(['GET'])
@permission_classes([RoleMatrixPermission.for_module('vehicles', {'GET': 'export'})])
def export_vehicles_csv_api(request):
    return views.export_vehicles_csv(request)


@api_view(['GET'])
@permission_classes([RoleMatrixPermission.for_module('equipment', {'GET': 'export'})])
def export_equipment_csv_api(request):
    return views.export_equipment_csv(request)


@api_view(['POST'])
@authentication_classes([TokenAuthentication, BasicAuthentication])
@permission_classes([RoleMatrixPermission.for_module('vehicles')])
@parser_classes([parsers.MultiPartParser, parsers.FormParser])
def bulk_upload_assets_api(request):

    from .bulk_utils import parse_bulk_upload_csv, parse_excel_vehicles, parse_docx_vehicles, validate_vehicle_row

    csv_file = request.FILES.get('csv_file')
    excel_file = request.FILES.get('excel_file')
    docx_file = request.FILES.get('docx_file')
    selected_file = csv_file or excel_file or docx_file
    if not selected_file:
        return Response({'detail': 'Upload a CSV, Excel, or Word file.'}, status=status.HTTP_400_BAD_REQUEST)
    if selected_file.size > settings.FILE_UPLOAD_MAX_SIZE_MB * 1024 * 1024:
        return Response(
            {'detail': f'File too large. Maximum size: {settings.FILE_UPLOAD_MAX_SIZE_MB}MB'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if csv_file:
        rows, error = parse_bulk_upload_csv(csv_file)
    elif excel_file:
        rows, error = parse_excel_vehicles(excel_file)
    else:
        rows, error = parse_docx_vehicles(docx_file)
    if error:
        return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)

    created = 0
    errors = []
    for row_number, row in enumerate(rows, 1):
        validation_errors = validate_vehicle_row(row)
        if validation_errors:
            errors.append({'row': row_number, 'errors': validation_errors})
            continue

        vehicle_data = {
            'name': row.get('name', '').strip(),
            'make': row.get('make', '').strip() or None,
            'model': row.get('model', '').strip() or None,
            'vin_number': row.get('vin_number', '').strip() or None,
            'license_plate': row.get('license_plate', '').strip(),
            'asset_type': row.get('vehicle_type', 'car').strip() or 'car',
            'insurance_expiry': row.get('insurance_expiry') or None,
            'roadworthy_expiry': row.get('roadworthy_expiry') or None,
            'license_expiry': row.get('license_expiry') or None,
            'hackney_permit': row.get('hackney_permit') or None,
        }
        if vehicle_data['license_plate'] and Vehicle.objects.filter(
            license_plate=vehicle_data['license_plate']
        ).exists():
            errors.append({'row': row_number, 'errors': {'license_plate': 'This license plate already exists.'}})
            continue
        if vehicle_data['vin_number'] and Vehicle.objects.filter(
            vin_number=vehicle_data['vin_number']
        ).exists():
            errors.append({'row': row_number, 'errors': {'vin_number': 'This VIN already exists.'}})
            continue

        try:
            Vehicle.objects.create(**vehicle_data)
            created += 1
        except Exception as error:
            logger.exception('Bulk vehicle import failed on row %s', row_number)
            errors.append({'row': row_number, 'errors': {'detail': str(error)}})

    if created:
        views.log_audit(request.user, 'bulk_create', 'assets', description=f'Bulk uploaded {created} assets')
    return Response({'created': created, 'failed': len(errors), 'errors': errors})


@api_view(['POST'])
@authentication_classes([TokenAuthentication, BasicAuthentication])
@permission_classes([RoleMatrixPermission.for_module('equipment')])
@parser_classes([parsers.MultiPartParser, parsers.FormParser])
def bulk_upload_equipment_api(request):

    from .bulk_utils import parse_bulk_upload_csv, parse_Excel_equipment, validate_equipment_row

    csv_file = request.FILES.get('csv_file')
    excel_file = request.FILES.get('excel_file')
    selected_file = csv_file or excel_file
    if not selected_file:
        return Response({'detail': 'Upload a CSV or Excel file.'}, status=status.HTTP_400_BAD_REQUEST)
    if selected_file.size > settings.FILE_UPLOAD_MAX_SIZE_MB * 1024 * 1024:
        return Response(
            {'detail': f'File too large. Maximum size: {settings.FILE_UPLOAD_MAX_SIZE_MB}MB'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if csv_file:
        rows, error = parse_bulk_upload_csv(csv_file)
    else:
        rows, error = parse_Excel_equipment(excel_file)
    if error:
        return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)

    created = 0
    errors = []
    for row_number, row in enumerate(rows, 1):
        validation_errors = validate_equipment_row(row)
        if validation_errors:
            errors.append({'row': row_number, 'errors': validation_errors})
            continue

        purchase_date = row.get('purchase_date') or None
        year_of_purchase = row.get('year_of_purchase') or None
        if not purchase_date and year_of_purchase:
            try:
                purchase_date = f'{int(year_of_purchase)}-01-01'
            except (ValueError, TypeError):
                purchase_date = None

        equipment_data = {
            'name': row.get('name', '').strip(),
            'equipment_type': row.get('equipment_type', 'other').strip().lower(),
            'description': row.get('description', '').strip(),
            'location': row.get('location', 'Main Office').strip(),
            'status': row.get('status', 'active').strip().lower(),
            'purchase_date': purchase_date,
            'warranty_expiry': row.get('warranty_expiry') or None,
            'cost': row.get('cost') or None,
            'notes': row.get('notes', '').strip(),
            'subsidiary': row.get('subsidiary', 'Other').strip(),
            'serial_number': row.get('serial_number', '').strip() or None,
            'tag_number': row.get('tag_number', '').strip() or None,
            'assigned_user': row.get('assigned_user', '').strip() or None,
            'quantity': int(row.get('quantity', 1)) if row.get('quantity') else 1,
            'remarks': row.get('remarks', '').strip(),
        }
        try:
            OfficeEquipment.objects.create(**equipment_data)
            created += 1
        except Exception as error:
            logger.exception('Bulk equipment import failed on row %s', row_number)
            errors.append({'row': row_number, 'errors': {'detail': str(error)}})

    if created:
        views.log_audit(
            request.user,
            'bulk_create',
            'office_equipment',
            description=f'Bulk uploaded {created} equipment items',
        )
    return Response({'created': created, 'failed': len(errors), 'errors': errors})
