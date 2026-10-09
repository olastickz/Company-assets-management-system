from datetime import datetime
import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .email_notifications import send_expiry_alerts
from .models import (
    Asset,
    AssetAssignmentHistory,
    AuditLog,
    CompanyDocument,
    CompanyAsset,
    EmailDeliveryLog,
    EmailRecipient,
    EmailSchedule,
    EquipmentTransfer,
    MaintenanceItem,
    OfficeEquipment,
    OfficeEquipmentMaintenance,
    StaffMember,
    UserRole,
)
from .permissions import get_user_role
from .serializers import AdminUserSerializer, NotificationRecipientSerializer, StaffMemberSerializer
from .staff_onboarding import provision_staff_account

logger = logging.getLogger(__name__)


class ManagerPermission(IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and get_user_role(request.user) in {
            'admin', 'manager'
        }


class AdminPermission(IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and (
            request.user.is_superuser or get_user_role(request.user) == 'admin'
        )


class AdminPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class AdminUsersView(APIView):
    permission_classes = [AdminPermission]
    pagination_class = AdminPagination

    def get(self, request):
        users = User.objects.select_related('role').order_by('username')
        search = request.query_params.get('search')
        if search:
            users = users.filter(
                Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )
        role = request.query_params.get('role')
        if role == 'admin':
            users = users.filter(Q(role__role='admin') | Q(is_superuser=True))
        elif role == 'staff':
            users = users.filter(Q(role__role='staff') | Q(role__isnull=True))
        elif role:
            users = users.filter(role__role=role)
        active = request.query_params.get('is_active')
        if active in ('true', 'false'):
            users = users.filter(is_active=(active == 'true'))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(users, request, view=self)
        return paginator.get_paginated_response(AdminUserSerializer(page, many=True).data)

    def post(self, request):
        serializer = AdminUserSerializer(data=request.data)
        if serializer.is_valid():
            return self._create(serializer)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def _create(serializer):
        user = serializer.save()
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)


class AdminUserDetailView(APIView):
    permission_classes = [AdminPermission]

    def get(self, request, user_id):
        user = get_object_or_404(User.objects.select_related('role'), pk=user_id)
        return Response(AdminUserSerializer(user).data)

    def patch(self, request, user_id):
        user = get_object_or_404(User.objects.select_related('role'), pk=user_id)
        if user.is_superuser:
            return Response({'detail': 'Django superuser accounts cannot be changed through this API.'}, status=status.HTTP_403_FORBIDDEN)
        if user.pk == request.user.pk and request.data.get('is_active') is False:
            return Response({'is_active': 'You cannot deactivate your own account.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = AdminUserSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            return Response(AdminUserSerializer(serializer.save()).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminRolesView(APIView):
    permission_classes = [AdminPermission]

    def get(self, request):
        return Response([
            {'value': value, 'label': label}
            for value, label in UserRole.ROLE_CHOICES
        ])


class AdminStaffListView(generics.ListCreateAPIView):
    permission_classes = [AdminPermission]
    serializer_class = StaffMemberSerializer
    pagination_class = AdminPagination

    def get_queryset(self):
        staff = StaffMember.objects.select_related('user').order_by('staff_id')
        search = self.request.query_params.get('search')
        if search:
            staff = staff.filter(
                Q(staff_id__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )
        for field in ('department', 'branch', 'driver_status'):
            value = self.request.query_params.get(field)
            if value:
                staff = staff.filter(**{field: value})
        active = self.request.query_params.get('is_active')
        if active in ('true', 'false'):
            staff = staff.filter(is_active=(active == 'true'))
        return staff

    def create(self, request, *args, **kwargs):
        staff_data = request.data.copy()
        staff_data.pop('user', None)
        staff_data.pop('is_active', None)
        serializer = self.get_serializer(data=staff_data)
        serializer.is_valid(raise_exception=True)
        staff = StaffMember(**serializer.validated_data)

        try:
            provision_staff_account(staff, request)
        except ValidationError as error:
            if hasattr(error, 'message_dict'):
                return Response(error.message_dict, status=status.HTTP_400_BAD_REQUEST)
            return Response({'detail': error.messages}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception('Failed to create an admin-provisioned staff account')
            return Response(
                {'detail': 'The staff account could not be created or its setup email could not be sent.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        response_data = self.get_serializer(staff).data
        response_data['account_status'] = 'pending_password'
        response_data['setup_email_sent'] = True
        return Response(response_data, status=status.HTTP_201_CREATED)


class AdminStaffDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [AdminPermission]
    queryset = StaffMember.objects.select_related('user').all()
    serializer_class = StaffMemberSerializer


def serialize_user(user):
    return {
        'id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
    }


def serialize_vehicle(vehicle):
    return {
        'id': vehicle.id,
        'name': vehicle.name,
        'license_plate': vehicle.license_plate,
        'make': vehicle.make,
        'model': vehicle.model,
        'asset_type': vehicle.asset_type,
        'status': vehicle.status,
        'cost': vehicle.cost,
        'assigned_staff': str(vehicle.assigned_staff) if vehicle.assigned_staff else None,
        'insurance_expiry': vehicle.insurance_expiry,
        'roadworthy_expiry': vehicle.roadworthy_expiry,
        'license_expiry': vehicle.license_expiry,
    }


def serialize_equipment(equipment):
    return {
        'id': equipment.id,
        'name': equipment.name,
        'equipment_type': equipment.equipment_type,
        'status': equipment.status,
        'cost': equipment.cost,
        'quantity': equipment.quantity,
        'location': equipment.location,
        'regional_office': equipment.regional_office,
        'subsidiary': equipment.subsidiary,
        'assigned_to': equipment.assigned_to_display,
        'warranty_expiry': equipment.warranty_expiry,
    }


def serialize_document(document):
    return {
        'id': document.id,
        'name': document.name,
        'document_type': document.document_type,
        'status': document.status,
        'issue_date': document.issue_date,
        'expiry_date': document.expiry_date,
        'renewal_date': document.renewal_date,
        'document_number': document.document_number,
        'related_asset': document.asset_display,
        'document_file': document.document_file.url if document.document_file else None,
    }


def serialize_maintenance(item, equipment=False):
    return {
        'id': item.id,
        'asset_id': item.equipment_id if equipment else item.vehicle_id,
        'asset_name': str(item.equipment if equipment else item.vehicle),
        'description': item.description,
        'date': item.maintenance_date if equipment else item.date_performed,
        'due_date': item.due_date if equipment else None,
        'cost': item.cost,
        'notes': item.notes,
    }


class OverviewReportView(APIView):
    permission_classes = [ManagerPermission]

    def get(self, request):
        today = timezone.now().date()
        return Response({
            'generated_at': timezone.now(),
            'assets': {
                'total': Asset.objects.count(),
                'active': Asset.objects.filter(status='active').count(),
                'unassigned': Asset.objects.filter(assigned_staff__isnull=True).count(),
            },
            'vehicles': CompanyAsset.objects.count(),
            'equipment': OfficeEquipment.objects.count(),
            'documents': {
                'total': CompanyDocument.objects.count(),
                'expired': CompanyDocument.objects.filter(expiry_date__lt=today).count(),
                'expiring': CompanyDocument.objects.filter(
                    expiry_date__gte=today,
                    expiry_date__lte=today + timezone.timedelta(days=30),
                ).count(),
            },
            'maintenance': {
                'vehicle_cost': MaintenanceItem.objects.aggregate(total=Sum('cost'))['total'] or 0,
                'equipment_cost': OfficeEquipmentMaintenance.objects.aggregate(total=Sum('cost'))['total'] or 0,
            },
        })


class VehicleReportView(APIView):
    permission_classes = [ManagerPermission]

    def get(self, request):
        queryset = CompanyAsset.objects.all().order_by('name')
        if request.query_params.get('status'):
            queryset = queryset.filter(status=request.query_params['status'])
        return Response({'count': queryset.count(), 'results': [serialize_vehicle(item) for item in queryset]})


class EquipmentReportView(APIView):
    permission_classes = [ManagerPermission]

    def get(self, request):
        queryset = OfficeEquipment.objects.all().order_by('name')
        if request.query_params.get('status'):
            queryset = queryset.filter(status=request.query_params['status'])
        if request.query_params.get('regional_office'):
            queryset = queryset.filter(regional_office=request.query_params['regional_office'])
        return Response({'count': queryset.count(), 'results': [serialize_equipment(item) for item in queryset]})


class DocumentReportView(APIView):
    permission_classes = [ManagerPermission]

    def get(self, request):
        today = timezone.now().date()
        queryset = CompanyDocument.objects.all().order_by('expiry_date')
        status_filter = request.query_params.get('expiry_status')
        if status_filter == 'expired':
            queryset = queryset.filter(expiry_date__lt=today)
        elif status_filter == 'expiring':
            queryset = queryset.filter(expiry_date__gte=today, expiry_date__lte=today + timezone.timedelta(days=30))
        return Response({'count': queryset.count(), 'results': [serialize_document(item) for item in queryset]})


class MaintenanceReportView(APIView):
    permission_classes = [ManagerPermission]

    def get(self, request):
        vehicle_items = MaintenanceItem.objects.select_related('vehicle').all()
        equipment_items = OfficeEquipmentMaintenance.objects.select_related('equipment').all()
        return Response({
            'summary': {
                'vehicle_count': vehicle_items.count(),
                'equipment_count': equipment_items.count(),
                'vehicle_cost': vehicle_items.aggregate(total=Sum('cost'))['total'] or 0,
                'equipment_cost': equipment_items.aggregate(total=Sum('cost'))['total'] or 0,
            },
            'vehicles': [serialize_maintenance(item) for item in vehicle_items],
            'equipment': [serialize_maintenance(item, equipment=True) for item in equipment_items],
        })


class TransferReportView(APIView):
    permission_classes = [ManagerPermission]

    def get(self, request):
        transfers = EquipmentTransfer.objects.select_related('equipment').all()
        return Response({'count': transfers.count(), 'results': [
            {
                'id': item.id,
                'equipment': str(item.equipment),
                'transferred_from': item.transferred_from,
                'transferred_to': item.transferred_to,
                'transfer_date': item.transfer_date,
                'reason': item.reason,
            }
            for item in transfers
        ]})


class AuditReportView(APIView):
    permission_classes = [ManagerPermission]

    def get(self, request):
        logs = AuditLog.objects.select_related('user').all()
        if request.query_params.get('action'):
            logs = logs.filter(action=request.query_params['action'])
        if request.query_params.get('model_name'):
            logs = logs.filter(model_name__icontains=request.query_params['model_name'])
        if request.query_params.get('user'):
            logs = logs.filter(user__username__icontains=request.query_params['user'])
        paginator = AdminPagination()
        page = paginator.paginate_queryset(logs, request, view=self)
        results = [
            {
                'id': item.id,
                'user': item.user.username if item.user else None,
                'action': item.action,
                'model_name': item.model_name,
                'object_id': item.object_id,
                'description': item.description,
                'ip_address': item.ip_address,
                'timestamp': item.timestamp,
            }
            for item in page
        ]
        return paginator.get_paginated_response(results)


class NotificationScheduleView(APIView):
    permission_classes = [AdminPermission]

    def get_schedule(self):
        schedule, _ = EmailSchedule.objects.get_or_create()
        return schedule

    def serialize(self, schedule):
        return {
            'id': schedule.id,
            'schedule_time': schedule.schedule_time,
            'alert_days': schedule.alert_days,
            'is_enabled': schedule.is_enabled,
            'last_sent': schedule.last_sent,
            'updated_at': schedule.updated_at,
        }

    def get(self, request):
        return Response(self.serialize(self.get_schedule()))

    def patch(self, request):
        schedule = self.get_schedule()
        if 'schedule_time' in request.data:
            try:
                schedule.schedule_time = datetime.strptime(
                    request.data['schedule_time'], '%H:%M:%S'
                ).time()
            except (TypeError, ValueError):
                return Response(
                    {'schedule_time': 'Use HH:MM:SS format.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if 'alert_days' in request.data:
            try:
                schedule.alert_days = int(request.data['alert_days'])
            except (TypeError, ValueError):
                return Response(
                    {'alert_days': 'Use a non-negative integer.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if schedule.alert_days < 0:
                return Response(
                    {'alert_days': 'Use a non-negative integer.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if 'is_enabled' in request.data:
            enabled = request.data['is_enabled']
            if isinstance(enabled, bool):
                schedule.is_enabled = enabled
            elif isinstance(enabled, str) and enabled.lower() in ('true', 'false'):
                schedule.is_enabled = enabled.lower() == 'true'
            else:
                return Response(
                    {'is_enabled': 'Use a boolean value.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        schedule.updated_by = request.user
        schedule.save()
        return Response(self.serialize(schedule))


class NotificationRecipientsView(APIView):
    permission_classes = [AdminPermission]

    def get(self, request):
        recipients = EmailRecipient.objects.all().order_by('email')
        search = request.query_params.get('search')
        if search:
            recipients = recipients.filter(
                Q(email__icontains=search) | Q(full_name__icontains=search)
            )
        active = request.query_params.get('is_active')
        if active in ('true', 'false'):
            recipients = recipients.filter(is_active=(active == 'true'))
        paginator = AdminPagination()
        page = paginator.paginate_queryset(recipients, request, view=self)
        return paginator.get_paginated_response(
            NotificationRecipientSerializer(page, many=True).data
        )

    def post(self, request):
        serializer = NotificationRecipientSerializer(data=request.data)
        if serializer.is_valid():
            recipient = serializer.save(created_by=request.user)
            return Response(
                NotificationRecipientSerializer(recipient).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class NotificationRecipientDetailView(APIView):
    permission_classes = [AdminPermission]

    def get(self, request, recipient_id):
        recipient = get_object_or_404(EmailRecipient, pk=recipient_id)
        return Response(NotificationRecipientSerializer(recipient).data)

    def patch(self, request, recipient_id):
        recipient = get_object_or_404(EmailRecipient, pk=recipient_id)
        serializer = NotificationRecipientSerializer(recipient, data=request.data, partial=True)
        if serializer.is_valid():
            return Response(NotificationRecipientSerializer(serializer.save()).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, recipient_id):
        recipient = get_object_or_404(EmailRecipient, pk=recipient_id)
        recipient.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationDeliveriesView(APIView):
    permission_classes = [ManagerPermission]

    def get(self, request):
        logs = EmailDeliveryLog.objects.all()
        if request.query_params.get('status'):
            logs = logs.filter(status=request.query_params['status'])
        return Response({'count': logs.count(), 'results': [
            {
                'id': item.id,
                'recipient_email': item.recipient_email,
                'subject': item.subject,
                'status': item.status,
                'message': item.message,
                'error_message': item.error_message,
                'sent_at': item.sent_at,
                'created_at': item.created_at,
            }
            for item in logs[:500]
        ]})


class SendNotificationNowView(APIView):
    permission_classes = [AdminPermission]

    def post(self, request):
        return Response(send_expiry_alerts())


class NotificationRetryView(APIView):
    permission_classes = [AdminPermission]

    def post(self, request, delivery_id):
        delivery = EmailDeliveryLog.objects.get(pk=delivery_id)
        delivery.status = 'queued'
        delivery.error_message = None
        delivery.save(update_fields=['status', 'error_message'])
        return Response({'id': delivery.id, 'status': delivery.status})


class OrganizationSettingsView(APIView):
    permission_classes = [ManagerPermission]

    def get(self, request):
        return Response({
            'name': getattr(settings, 'ORGANIZATION_NAME', 'Telnet Asset Management'),
            'timezone': settings.TIME_ZONE,
            'file_upload_max_size_mb': settings.FILE_UPLOAD_MAX_SIZE_MB,
        })


class NotificationSettingsView(NotificationScheduleView):
    pass


class ProfileSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(serialize_user(request.user))

    def patch(self, request):
        user = request.user
        for field in ('first_name', 'last_name', 'email'):
            if field in request.data:
                setattr(user, field, request.data[field])
        user.save(update_fields=['first_name', 'last_name', 'email'])
        return Response(serialize_user(user))
