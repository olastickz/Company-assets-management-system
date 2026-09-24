from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import status
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
)
from .permissions import get_user_role


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
        return Response({'count': logs.count(), 'results': [
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
            for item in logs[:500]
        ]})


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
        recipients = EmailRecipient.objects.all()
        return Response({'count': recipients.count(), 'results': [self.serialize(item) for item in recipients]})

    def post(self, request):
        recipient = EmailRecipient.objects.create(
            email=request.data.get('email'),
            full_name=request.data.get('full_name', ''),
            is_active=request.data.get('is_active', True),
            created_by=request.user,
        )
        return Response(self.serialize(recipient), status=status.HTTP_201_CREATED)

    @staticmethod
    def serialize(recipient):
        return {
            'id': recipient.id,
            'email': recipient.email,
            'full_name': recipient.full_name,
            'is_active': recipient.is_active,
            'created_at': recipient.created_at,
        }


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
