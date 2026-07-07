from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse as django_reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib.auth import logout
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import models, transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.conf import settings
from datetime import timedelta, date
import csv
import logging
from openpyxl import Workbook
import uuid
from urllib.parse import urlencode, urlparse, parse_qs
from .models import CompanyAsset, Vehicle, MaintenanceItem, OfficeEquipment, OfficeEquipmentMaintenance, AuditLog, CompanyDocument, EquipmentTransfer, StaffMember, Asset, AssetRelationship

# Logger for application events
logger = logging.getLogger(__name__)
from .forms import CompanyAssetForm, VehicleForm, MaintenanceItemForm, OfficeEquipmentForm, OfficeEquipmentMaintenanceForm, EquipmentTransferForm, CompanyDocumentForm, StaffMemberForm
from .permissions import (
    require_admin, require_manager, is_admin, is_manager, is_driver,
    get_user_role, log_audit, get_client_ip
)


class CustomLoginView(LoginView):
    template_name = 'login.html'
    redirect_authenticated_user = False

    def form_valid(self, form):
        """Handle login with optional 'remember me' functionality."""
        remember_me = self.request.POST.get('remember_me')
        timeout = settings.SESSION_TIMEOUT_MANAGER if remember_me else settings.SESSION_TIMEOUT_USER
        self.request.session.set_expiry(timeout)
        self.request.session.modified = True
        
        # Log login
        try:
            log_audit(
                form.get_user(),
                'login',
                'auth',
                description="User logged in",
                ip_address=get_client_ip(self.request)
            )
        except Exception as e:
            logger.warning(f"Failed to log login event: {e}")
        
        return super().form_valid(form)


# ----------------------------
# Custom Logout view (handles GET requests)
# ----------------------------
def custom_logout(request):
    logout(request)
    return redirect('login')


def get_vehicle_status(vehicle, today, expiring_threshold):
    expiry_dates = [
        getattr(vehicle, field)
        for field in ('insurance_expiry', 'roadworthy_expiry', 'license_expiry', 'hackney_permit')
        if getattr(vehicle, field)
    ]

    if any(expiry < today for expiry in expiry_dates):
        return 'expired'
    if any(expiry <= expiring_threshold for expiry in expiry_dates):
        return 'expiring'
    return 'safe'


def get_equipment_status(equipment, today, expiring_threshold):
    expiry = equipment.warranty_expiry
    if not expiry:
        return 'unknown'
    if expiry < today:
        return 'expired'
    if expiry <= expiring_threshold:
        return 'expiring'
    return 'safe'


def get_vehicle_next_expiry(vehicle):
    expiries = [
        getattr(vehicle, field)
        for field in ('insurance_expiry', 'roadworthy_expiry', 'license_expiry', 'hackney_permit')
        if getattr(vehicle, field)
    ]
    return min(expiries) if expiries else None


def _normalize_staff_name(name):
    return name.strip().lower()


def _split_name(full_name):
    parts = full_name.strip().split()
    if len(parts) <= 1:
        return parts[0], ''
    return parts[0], ' '.join(parts[1:])


def _normalize_name(name):
    return ' '.join(name.strip().lower().split()) if name else ''


def _assigned_user_matches_current_user(equipment, user):
    if not equipment.assigned_user or not user.is_authenticated:
        return False

    assigned_user = _normalize_name(equipment.assigned_user)
    candidates = {user.username.strip().lower()}
    if user.first_name or user.last_name:
        full_name = f"{user.first_name} {user.last_name}".strip()
        if full_name:
            candidates.add(_normalize_name(full_name))
            candidates.add(_normalize_name(f"{user.last_name} {user.first_name}".strip()))
        if user.first_name:
            candidates.add(user.first_name.strip().lower())
        if user.last_name:
            candidates.add(user.last_name.strip().lower())

    staff_profile = getattr(user, 'staff_profile', None)
    if staff_profile:
        candidates.add(_normalize_name(staff_profile.full_name))
        candidates.add(staff_profile.staff_id.strip().lower())

    return assigned_user in candidates


def _generate_legacy_staff_id(name):
    base = ''.join(ch for ch in name.upper() if ch.isalnum())[:8] or 'LEGACY'
    return f"{base}-{uuid.uuid4().hex[:4]}"


def get_legacy_assigned_names():
    equipment_names = set(
        OfficeEquipment.objects.exclude(assigned_user__isnull=True)
        .exclude(assigned_user__exact='')
        .values_list('assigned_user', flat=True)
    )
    document_names = set(
        CompanyDocument.objects.exclude(responsible_person__isnull=True)
        .exclude(responsible_person__exact='')
        .values_list('responsible_person', flat=True)
    )
    legacy = {
        name.strip()
        for name in equipment_names | document_names
        if name and name.strip()
    }
    return sorted(legacy)


def get_back_url(request, default_url='/'):
    """Build a safe local back URL from the HTTP referrer."""
    referrer = request.META.get('HTTP_REFERER', '')
    if not referrer:
        return default_url
    try:
        parsed = urlparse(referrer)
    except ValueError:
        return default_url
    if parsed.netloc and parsed.netloc != request.get_host():
        return default_url
    path = parsed.path or '/'
    if not path.startswith('/'):
        return default_url
    if parsed.query:
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        query_string = urlencode({k: v[0] for k, v in query_params.items()}, doseq=False)
        return f"{path}?{query_string}" if query_string else path
    return path


# ----------------------------
# Send expiry alerts view
# ----------------------------
@login_required
@require_admin
def send_expiry_alerts_view(request):
    from .email_notifications import send_expiry_alerts
    result = send_expiry_alerts()
    if result['status'] == 'sent':
        messages.success(request, f"Expiry alert email sent to {', '.join(result.get('recipients', []))}")
    elif result['status'] == 'no_alerts':
        messages.info(request, result['message'])
    else:
        messages.error(request, result.get('message', 'Failed to send expiry alert email'))
    return redirect('dashboard')


# ----------------------------
# Dashboard view
# ----------------------------
@login_required
def dashboard(request):
    """Display a unified assets dashboard with optional filtering for vehicles and equipment."""
    search_query = request.GET.get('search', '')
    current_filter = request.GET.get('filter', '')
    asset_type = request.GET.get('asset_type', 'all')
    assigned_filter = request.GET.get('assigned_filter', '')
    status_filter = request.GET.getlist('status')
    category_filter = request.GET.getlist('category')
    sort_by = request.GET.get('sort_by', 'expiry')
    sort_dir = request.GET.get('sort_dir', 'asc')
    page_num = request.GET.get('page', 1)

    query_string = request.GET.urlencode()
    page_query_params = request.GET.copy()
    page_query_params.pop('page', None)
    pagination_query_string = page_query_params.urlencode()

    try:
        page_size = int(request.GET.get('page_size', settings.VEHICLES_PER_PAGE))
    except (TypeError, ValueError):
        page_size = settings.VEHICLES_PER_PAGE
    if page_size not in [10, 25, 50]:
        page_size = settings.VEHICLES_PER_PAGE

    if not current_filter and len(status_filter) == 1:
        current_filter = status_filter[0]

    today = timezone.now().date()

    # Get alert days from EmailSchedule
    try:
        from .models import EmailSchedule
        schedule = EmailSchedule.objects.first()
        alert_days = schedule.alert_days if schedule else settings.DEFAULT_ALERT_DAYS
    except Exception as e:
        logger.warning(f"Failed to fetch EmailSchedule: {e}")
        alert_days = settings.DEFAULT_ALERT_DAYS

    expiring_threshold = today + timedelta(days=alert_days)

    # Query vehicles (now CompanyAsset), equipment, and company documents
    vehicles = CompanyAsset.objects.all().order_by('-updated_at')
    equipments = OfficeEquipment.objects.all().order_by('-updated_at')
    documents = CompanyDocument.objects.all().order_by('-updated_at')
    staff_members = StaffMember.objects.filter(is_active=True).order_by('staff_id')
    assigned_staff_id = request.GET.get('assigned_staff', '')
    department_filter = request.GET.get('department', '')
    branch_filter = request.GET.get('branch', '')

    current_role = get_user_role(request.user)
    staff_profile = getattr(request.user, 'staff_profile', None)
    if current_role in ['staff', 'driver']:
        if staff_profile is not None:
            assigned_staff_id = str(staff_profile.pk)
            vehicles = vehicles.filter(assigned_staff=staff_profile)
            equipments = equipments.filter(assigned_staff=staff_profile)
            documents = documents.filter(
                Q(responsible_staff=staff_profile) |
                Q(related_asset__assigned_staff=staff_profile) |
                Q(related_vehicle__assigned_staff=staff_profile) |
                Q(related_equipment__assigned_staff=staff_profile)
            ).distinct()
        else:
            vehicles = CompanyAsset.objects.none()
            equipments = OfficeEquipment.objects.none()
            documents = CompanyDocument.objects.none()

    # If the current user is a Department Manager and no department filter
    # was provided, default the view to their department for scoped visibility.
    try:
        if not department_filter and current_role == 'manager' and hasattr(request.user, 'role'):
            dept = request.user.role.department
            if dept:
                department_filter = dept
    except Exception:
        # Fail closed to avoid breaking dashboard for anonymous or system users
        department_filter = department_filter

    if assigned_staff_id and current_role not in ['staff', 'driver']:
        vehicles = vehicles.filter(assigned_staff_id=assigned_staff_id)
        equipments = equipments.filter(assigned_staff_id=assigned_staff_id)
        documents = documents.filter(
            Q(responsible_staff_id=assigned_staff_id) |
            Q(related_asset__assigned_staff_id=assigned_staff_id) |
            Q(related_vehicle__assigned_staff_id=assigned_staff_id) |
            Q(related_equipment__assigned_staff_id=assigned_staff_id)
        ).distinct()

    if department_filter:
        vehicles = vehicles.filter(assigned_staff__department=department_filter)
        equipments = equipments.filter(assigned_staff__department=department_filter)
        documents = documents.filter(
            Q(responsible_staff__department=department_filter) |
            Q(related_asset__assigned_staff__department=department_filter) |
            Q(related_vehicle__assigned_staff__department=department_filter) |
            Q(related_equipment__assigned_staff__department=department_filter)
        ).distinct()

    if branch_filter:
        vehicles = vehicles.filter(assigned_staff__branch=branch_filter)
        equipments = equipments.filter(assigned_staff__branch=branch_filter)
        documents = documents.filter(
            Q(responsible_staff__branch=branch_filter) |
            Q(related_asset__assigned_staff__branch=branch_filter) |
            Q(related_vehicle__assigned_staff__branch=branch_filter) |
            Q(related_equipment__assigned_staff__branch=branch_filter)
        ).distinct()

    if search_query:
        vehicles = vehicles.filter(
            models.Q(name__icontains=search_query) |
            models.Q(license_plate__icontains=search_query) |
            models.Q(vin_number__icontains=search_query) |
            models.Q(make__icontains=search_query) |
            models.Q(model__icontains=search_query)
        )
        equipments = equipments.filter(
            models.Q(name__icontains=search_query) |
            models.Q(serial_number__icontains=search_query) |
            models.Q(tag_number__icontains=search_query) |
            models.Q(assigned_user__icontains=search_query) |
            models.Q(assigned_staff__staff_id__icontains=search_query) |
            models.Q(assigned_staff__first_name__icontains=search_query) |
            models.Q(assigned_staff__last_name__icontains=search_query) |
            models.Q(description__icontains=search_query)
        )
        documents = documents.filter(
            models.Q(name__icontains=search_query) |
            models.Q(document_number__icontains=search_query) |
            models.Q(issuing_authority__icontains=search_query) |
            models.Q(description__icontains=search_query) |
            models.Q(responsible_person__icontains=search_query) |
            models.Q(responsible_staff__staff_id__icontains=search_query) |
            models.Q(responsible_staff__first_name__icontains=search_query) |
            models.Q(responsible_staff__last_name__icontains=search_query)
        )

    def build_asset_item(obj, asset_kind, qs=None):
        if asset_kind == 'vehicle':
            status = get_vehicle_status(obj, today, expiring_threshold)
            expiry = get_vehicle_next_expiry(obj)
            detail_url = django_reverse('asset_detail', kwargs={'pk': obj.id})
            edit_url = django_reverse('asset_update', kwargs={'pk': obj.id})
            delete_url = django_reverse('asset_delete', kwargs={'pk': obj.id})
            identifier = obj.vin_number or obj.license_plate or obj.get_vehicle_type_display()
            return {
                'id': obj.id,
                'name': obj.name,
                'type': 'Vehicle',
                'type_label': obj.get_vehicle_type_display(),
                'category': obj.vehicle_type,
                'status': status,
                'status_label': status.title() if status != 'unknown' else 'No expiry',
                'expiry': expiry,
                'expiry_label': 'Next expiry',
                'assigned_to': str(obj.assigned_staff) if obj.assigned_staff else 'Unassigned',
                'location': obj.license_plate or 'N/A',
                'created_at': obj.created_at,
                'updated_at': obj.updated_at,
                'detail_url': detail_url,
                'edit_url': edit_url,
                'delete_url': delete_url,
                'quick_summary': f"VIN: {obj.vin_number or 'N/A'} | Plate: {obj.license_plate or 'N/A'}",
                'identifier': identifier,
            }
        elif asset_kind == 'document':
            status = obj.get_status()
            detail_url = django_reverse('company_document_detail', kwargs={'pk': obj.id})
            edit_url = django_reverse('company_document_edit', kwargs={'pk': obj.id})
            delete_url = django_reverse('company_document_delete', kwargs={'pk': obj.id})
            return {
                'id': obj.id,
                'name': obj.name,
                'type': 'Document',
                'type_label': obj.get_document_type_display(),
                'category': obj.document_type,
                'status': status,
                'status_label': status.title() if status != 'unknown' else 'No expiry',
                'expiry': obj.expiry_date,
                'expiry_label': 'Expiry date',
                'assigned_to': obj.responsible_person or 'Unassigned',
                'location': obj.location or 'Unassigned',
                'created_at': obj.created_at,
                'updated_at': obj.updated_at,
                'detail_url': detail_url,
                'edit_url': edit_url,
                'delete_url': delete_url,
                'quick_summary': f"Doc#: {obj.document_number or 'N/A'} | Issuer: {obj.issuing_authority or 'N/A'}",
                'identifier': obj.document_number or obj.issuing_authority or obj.location or 'N/A',
            }
        else:  # equipment
            return {
                'id': obj.id,
                'name': obj.name,
                'type': 'Equipment',
                'type_label': obj.get_equipment_type_display(),
                'category': obj.equipment_type,
                'status': get_equipment_status(obj, today, expiring_threshold),
                'status_label': obj.get_status_display(),
                'expiry': obj.warranty_expiry,
                'expiry_label': 'Warranty expiry',
                'assigned_to': obj.assigned_user or 'Unassigned',
                'location': obj.location or 'Unassigned',
                'created_at': obj.created_at,
                'updated_at': obj.updated_at,
                'detail_url': django_reverse('equipment_detail', kwargs={'pk': obj.id}),
                'edit_url': django_reverse('equipment_update', kwargs={'pk': obj.id}),
                'delete_url': django_reverse('equipment_delete', kwargs={'pk': obj.id}),
                'quick_summary': f"Serial: {obj.serial_number or 'N/A'} | Location: {obj.location or 'N/A'}",
                'identifier': obj.serial_number or obj.location or 'N/A',
            }



    asset_items = []
    for vehicle in vehicles:
        asset_items.append(build_asset_item(vehicle, 'vehicle', query_string))
    for equipment in equipments:
        asset_items.append(build_asset_item(equipment, 'equipment', query_string))
    for document in documents:
        asset_items.append(build_asset_item(document, 'document', query_string))

    vehicle_count = vehicles.count()
    equipment_count = equipments.count()
    document_count = documents.count()

    if status_filter:
        asset_items = [asset for asset in asset_items if asset['status'] in status_filter]

    if category_filter:
        asset_items = [asset for asset in asset_items if asset['category'] in category_filter]

    # Filter by asset type (vehicles, equipment, documents, or all)
    if asset_type == 'vehicles':
        asset_items = [asset for asset in asset_items if asset['type'] == 'Vehicle']
    elif asset_type == 'equipment':
        asset_items = [asset for asset in asset_items if asset['type'] == 'Equipment']
    elif asset_type == 'documents':
        asset_items = [asset for asset in asset_items if asset['type'] == 'Document']

    total_assets_all = len(asset_items)
    unassigned_count_all = sum(1 for asset in asset_items if asset['assigned_to'] in ('Unassigned', 'N/A', ''))
    assigned_count_all = total_assets_all - unassigned_count_all
    available_count_all = unassigned_count_all
    assigned_percent_all = int((assigned_count_all / total_assets_all) * 100) if total_assets_all else 0
    available_percent_all = int((available_count_all / total_assets_all) * 100) if total_assets_all else 0
    inventory_breakdown = f"{vehicle_count} vehicles · {equipment_count} equipment · {document_count} documents"

    if assigned_filter == 'assigned':
        asset_items = [asset for asset in asset_items if asset['assigned_to'] not in ('Unassigned', 'N/A', '')]
    elif assigned_filter == 'unassigned':
        asset_items = [asset for asset in asset_items if asset['assigned_to'] in ('Unassigned', 'N/A', '')]

    total_assets = len(asset_items)
    unassigned_count = sum(1 for asset in asset_items if asset['assigned_to'] in ('Unassigned', 'N/A', ''))
    assigned_count = total_assets - unassigned_count
    available_count = unassigned_count
    expired_count = sum(1 for asset in asset_items if asset['status'] == 'expired')
    expiring_count = sum(1 for asset in asset_items if asset['status'] == 'expiring')
    safe_count = sum(1 for asset in asset_items if asset['status'] == 'safe')
    unknown_count = sum(1 for asset in asset_items if asset['status'] == 'unknown')

    if current_filter == 'expired':
        asset_items = [asset for asset in asset_items if asset['status'] == 'expired']
    elif current_filter == 'expiring':
        asset_items = [asset for asset in asset_items if asset['status'] == 'expiring']
    elif current_filter == 'safe':
        asset_items = [asset for asset in asset_items if asset['status'] == 'safe']

    reverse = sort_dir == 'desc'
    if sort_by == 'status':
        priority = {'expired': 0, 'expiring': 1, 'safe': 2, 'unknown': 3}
        asset_items.sort(key=lambda x: (priority.get(x['status'], 3), x['type'], x['name']), reverse=reverse)
    elif sort_by == 'type':
        asset_items.sort(key=lambda x: (x['type'], x['name']), reverse=reverse)
    elif sort_by == 'created':
        asset_items.sort(key=lambda x: x['created_at'] or date.min, reverse=reverse)
    else:
                    asset_items.sort(key=lambda x: (x['expiry'] if x['expiry'] else date.max, x['type'], x['name']), reverse=reverse)

    last_updated = max((asset['updated_at'] for asset in asset_items), default=today)
    critical_assets = sorted(
        [asset for asset in asset_items if asset['status'] in ('expired', 'expiring')],
        key=lambda x: x['expiry'] or date.max
    )[:5]
    recent_assets = sorted(asset_items, key=lambda x: x['created_at'] or date.min, reverse=True)[:5]

    chart_type_data = {
        'Vehicle': sum(1 for asset in asset_items if asset['type'] == 'Vehicle'),
        'Equipment': sum(1 for asset in asset_items if asset['type'] == 'Equipment'),
        'Document': sum(1 for asset in asset_items if asset['type'] == 'Document'),
    }
    chart_status_data = {
        'Expired': expired_count,
        'Expiring': expiring_count,
        'Safe': safe_count,
        'No expiry': unknown_count,
    }

    paginator = Paginator(asset_items, page_size)
    try:
        page_obj = paginator.page(page_num)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    # Pass query string to detail templates for back navigation
    for asset in page_obj:
        if 'detail_url' in asset and query_string:
            separator = '&' if '?' in asset['detail_url'] else '?'
            asset['detail_url'] += separator + query_string

    maintenance_items = OfficeEquipmentMaintenance.objects.select_related('equipment').order_by('-maintenance_date')
    m_expired = maintenance_items.filter(due_date__lt=today)
    m_expiring = maintenance_items.filter(due_date__gte=today, due_date__lte=expiring_threshold)
    pending_maintenance_count = maintenance_items.filter(due_date__gte=today).count()
    maintenance_status_text = 'No maintenance due' if pending_maintenance_count == 0 else f'{pending_maintenance_count} due soon'
    maintenance_fill_percent = min(int((pending_maintenance_count / total_assets_all) * 100), 100) if total_assets_all else 0
    next_maintenance = maintenance_items.filter(due_date__gte=today).order_by('due_date').first()

    active_equipment_count = sum(
        1 for equipment in equipments
        if get_equipment_status(equipment, today, expiring_threshold) in ('safe', 'expiring')
    )
    equipment_due_count = sum(
        1 for equipment in equipments
        if get_equipment_status(equipment, today, expiring_threshold) in ('expired', 'expiring')
    )
    equipment_transfers = EquipmentTransfer.objects.count()

    recent_documents_count = documents.filter(created_at__gte=today - timedelta(days=30)).count()
    expiring_documents_count = documents.filter(expiry_date__gte=today, expiry_date__lte=expiring_threshold).count()
    pending_documents_count = documents.filter(status='pending_renewal').count()

    verified_count = total_assets - unknown_count
    verified_percent = int((verified_count / total_assets) * 100) if total_assets else 0
    chart_type_series = []
    max_type_count = max(chart_type_data.values(), default=0)
    for label, count in chart_type_data.items():
        chart_type_series.append({
            'label': label,
            'count': count,
            'height': int((count / max_type_count) * 100) if max_type_count else 0,
        })
    utilization_percent = int((assigned_count / total_assets) * 100) if total_assets else 0
    utilization_dashoffset = 402 - int(402 * utilization_percent / 100)

    dashboard_query = request.GET.copy()
    dashboard_query.pop('page', None)
    dashboard_query['assigned_filter'] = 'assigned'
    assigned_assets_url = f"{request.path}?{dashboard_query.urlencode()}"
    dashboard_query['assigned_filter'] = 'unassigned'
    available_assets_url = f"{request.path}?{dashboard_query.urlencode()}"
    maintenance_list_url = django_reverse('equipment_maintenance_list')

    category_options = [
        {'value': value, 'label': label}
        for value, label in Vehicle.VEHICLE_TYPE_CHOICES
    ] + [
        {'value': value, 'label': label}
        for value, label in OfficeEquipment.EQUIPMENT_TYPE_CHOICES
    ]
    status_options = [
        {'value': 'expired', 'label': 'Expired'},
        {'value': 'expiring', 'label': 'Expiring Soon'},
        {'value': 'safe', 'label': 'Safe'},
        {'value': 'unknown', 'label': 'No expiry'},
    ]

    department_options = [
        {'value': value, 'label': label}
        for value, label in StaffMember.DEPARTMENT_CHOICES
    ]
    branch_options = [
        {'value': value, 'label': label}
        for value, label in StaffMember.BRANCH_CHOICES
    ]

    return render(request, 'dashboard.html', {
        'asset_items': page_obj,
        'assets': page_obj,  # Add this for backward compatibility
        'total_assets_all': total_assets_all,
        'total_assets': total_assets,
        'vehicle_count': vehicle_count,
        'equipment_count': equipment_count,
        'document_count': document_count,
        'active_equipment_count': active_equipment_count,
        'equipment_due_count': equipment_due_count,
        'equipment_transfers': equipment_transfers,
        'recent_documents_count': recent_documents_count,
        'expiring_documents_count': expiring_documents_count,
        'pending_documents_count': pending_documents_count,
        'document_change': None,
        'recent_documents_change': None,
        'expiring_documents_change': None,
        'pending_documents_change': None,
        'equipment_change': None,
        'active_equipment_change': None,
        'due_maintenance_change': None,
        'transfer_change': None,
        'unassigned_count': unassigned_count,
        'assigned_count': assigned_count,
        'available_count': available_count,
        'expired_count': expired_count,
        'expiring_count': expiring_count,
        'safe_count': safe_count,
        'unknown_count': unknown_count,
        'pending_maintenance_count': pending_maintenance_count,
        'maintenance_status_text': maintenance_status_text,
        'maintenance_fill_percent': maintenance_fill_percent,
        'assigned_percent_all': assigned_percent_all,
        'available_percent_all': available_percent_all,
        'inventory_breakdown': inventory_breakdown,
        'assigned_assets_url': assigned_assets_url,
        'available_assets_url': available_assets_url,
        'maintenance_list_url': maintenance_list_url,
        'next_maintenance': next_maintenance,
        'verified_count': verified_count,
        'verified_percent': verified_percent,
        'chart_type_series': chart_type_series,
        'utilization_percent': utilization_percent,
        'utilization_dashoffset': utilization_dashoffset,
        'search_query': search_query,
        'current_filter': current_filter,
        'asset_type': asset_type,
        'status_filter': status_filter,
        'category_filter': category_filter,
        'sort_by': sort_by,
        'sort_dir': sort_dir,
        'page_size': page_size,
        'last_updated': last_updated,
        'critical_assets': critical_assets,
        'recent_assets': recent_assets,
        'chart_type_data': chart_type_data,
        'chart_status_data': chart_status_data,
        'category_options': category_options,
        'status_options': status_options,
        'department_options': department_options,
        'branch_options': branch_options,
        'page_size_options': [10, 25, 50],
        'query_string': query_string,
        'pagination_query_string': pagination_query_string,
        'today': today,
        'expiring_threshold': expiring_threshold,
        'paginator': paginator,
        'page_obj': page_obj,
        'staff_members': staff_members,
        'assigned_staff_id': assigned_staff_id,
        'department_filter': department_filter,
        'branch_filter': branch_filter,
    'active_staff_count': staff_members.count(),
    })


@login_required
def equipment_maintenance_list(request):
    today = timezone.now().date()
    maintenance_items = OfficeEquipmentMaintenance.objects.select_related('equipment').order_by('due_date')
    pending_count = maintenance_items.filter(due_date__gte=today).count()
    overdue_count = maintenance_items.filter(due_date__lt=today).count()

    return render(request, 'equipment_maintenance_list.html', {
        'maintenance_items': maintenance_items,
        'pending_count': pending_count,
        'overdue_count': overdue_count,
        'today': today,
    })


@login_required
@require_admin
def activity_dashboard(request):
    username = request.GET.get('user', '')
    action_filter = request.GET.get('action', '')
    model_filter = request.GET.get('model', '')

    logs = AuditLog.objects.all()

    if username:
        logs = logs.filter(user__username__icontains=username)
    if action_filter:
        logs = logs.filter(action=action_filter)
    if model_filter:
        logs = logs.filter(model_name__icontains=model_filter)

    paginator = Paginator(logs, 50)
    page_num = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_num)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    actions = AuditLog.ACTION_CHOICES

    return render(request, 'activity_dashboard.html', {
        'logs': page_obj,
        'username': username,
        'action_filter': action_filter,
        'model_filter': model_filter,
        'actions': actions,
        'paginator': paginator,
        'page_obj': page_obj,
    })


@login_required
@require_admin
def bulk_delete_assets(request):
    """Delete selected assets in bulk."""
    if request.method != 'POST':
        return redirect('dashboard')

    selected_ids = request.POST.getlist('selected')
    deleted_count = 0

    with transaction.atomic():
        for token in selected_ids:
            if ':' not in token:
                continue
            asset_kind, asset_id = token.split(':', 1)
            try:
                if asset_kind == 'vehicle':
                    obj = Vehicle.objects.get(pk=asset_id)
                elif asset_kind == 'equipment':
                    obj = OfficeEquipment.objects.get(pk=asset_id)
                else:
                    continue
                obj.delete()
                deleted_count += 1
                log_audit(request.user, 'delete', asset_kind, object_id=asset_id, description=f"Bulk deleted {asset_kind} {asset_id}", ip_address=get_client_ip(request))
            except (Vehicle.DoesNotExist, OfficeEquipment.DoesNotExist):
                continue

    if deleted_count:
        messages.success(request, f"Deleted {deleted_count} selected assets.")
    else:
        messages.info(request, "No selected assets were deleted.")

    return redirect('dashboard')


@login_required
@require_admin
def export_selected_assets_csv(request):
    """Export selected assets to a CSV file."""
    selected_ids = request.GET.getlist('selected')
    if not selected_ids:
        messages.info(request, 'Select assets before exporting.')
        return redirect('dashboard')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="selected_assets.csv"'
    writer = csv.writer(response)
    writer.writerow(['Asset Type', 'Name', 'Category', 'Status', 'Expiry', 'Assigned To', 'Location', 'Created Date'])

    for token in selected_ids:
        if ':' not in token:
            continue
        asset_kind, asset_id = token.split(':', 1)
        try:
            if asset_kind == 'vehicle':
                obj = Vehicle.objects.get(pk=asset_id)
                status = get_vehicle_status(obj)
                expiry = get_vehicle_next_expiry(obj)
                category = obj.get_asset_type_display()
                assigned_to = 'N/A'
                location = 'N/A'
            elif asset_kind == 'equipment':
                obj = OfficeEquipment.objects.get(pk=asset_id)
                status = get_equipment_status(obj)
                expiry = obj.warranty_expiry
                category = obj.get_equipment_type_display()
                assigned_to = obj.assigned_user or 'Unassigned'
                location = obj.location or 'Unassigned'
            else:
                continue
            writer.writerow([
                asset_kind.title(),
                obj.name,
                category,
                status.title(),
                expiry or 'N/A',
                assigned_to,
                location,
                obj.created_at.date() if hasattr(obj, 'created_at') else 'N/A'
            ])
        except (Vehicle.DoesNotExist, OfficeEquipment.DoesNotExist):
            continue

    return response


@login_required
@require_admin
def import_assets(request):
    """Admin CSV import for OfficeEquipment (basic). Accepts a CSV with headers:
    name,equipment_type,serial_number,warranty_expiry(YYYY-MM-DD),cost,subsidiary,location,status
    """
    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, 'No file uploaded.')
            return redirect('import_assets')

        try:
            decoded = csv_file.read().decode('utf-8').splitlines()
            reader = csv.DictReader(decoded)
        except Exception as e:
            messages.error(request, f'Failed to read CSV: {e}')
            return redirect('import_assets')

        created = 0
        for row in reader:
            name = row.get('name') or row.get('Name')
            if not name:
                continue
            equipment_defaults = {}
            equipment_defaults['equipment_type'] = row.get('equipment_type') or row.get('equipmentType') or ''
            equipment_defaults['serial_number'] = row.get('serial_number') or row.get('serial') or ''
            warranty = row.get('warranty_expiry') or row.get('warranty') or ''
            if warranty:
                try:
                    equipment_defaults['warranty_expiry'] = timezone.datetime.strptime(warranty.strip(), '%Y-%m-%d').date()
                except Exception:
                    equipment_defaults['warranty_expiry'] = None
            equipment_defaults['cost'] = float(row.get('cost') or 0) if (row.get('cost') and row.get('cost').strip()) else 0
            equipment_defaults['subsidiary'] = row.get('subsidiary') or ''
            equipment_defaults['location'] = row.get('location') or ''
            equipment_defaults['status'] = row.get('status') or 'active'

            obj, created_flag = OfficeEquipment.objects.get_or_create(name=name, defaults=equipment_defaults)
            if created_flag:
                created += 1

        messages.success(request, f'Imported {created} equipment items (duplicates skipped).')
        return redirect('dashboard')

    return render(request, 'import_assets.html', {})


# ----------------------------
# Vehicle detail view
# ----------------------------
@login_required
def vehicle_detail(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    maintenance_items = vehicle.maintenance_items.all()
    today = timezone.now().date()
    expiring_threshold = today + timedelta(days=30)
    assignment_history = vehicle.asset.assignments.all() if vehicle.asset else []
    related_assets = vehicle.asset.get_linked_assets() if vehicle.asset else []
    if vehicle.asset:
        asset_ids = [vehicle.asset.pk] + list(related_assets.values_list('pk', flat=True))
        related_documents = CompanyDocument.objects.filter(
            Q(related_vehicle=vehicle) |
            Q(related_asset__in=asset_ids)
        ).distinct().order_by('-expiry_date')
    else:
        related_documents = CompanyDocument.objects.filter(
            related_vehicle=vehicle
        ).order_by('-expiry_date')

    current_role = get_user_role(request.user)
    staff_profile = getattr(request.user, 'staff_profile', None)
    can_report_maintenance = False
    if current_role in ['admin', 'manager']:
        can_report_maintenance = True
    elif staff_profile and vehicle.assigned_staff == staff_profile:
        can_report_maintenance = True

    return render(request, 'asset_detail.html', {
        'vehicle': vehicle,
        'maintenance_items': maintenance_items,
        'today': today,
        'expiring_threshold': expiring_threshold,
        'assignment_history': assignment_history,
        'related_assets': related_assets,
        'related_documents': related_documents,
        'vehicle_type_choices': Vehicle.VEHICLE_TYPE_CHOICES,
        'can_report_maintenance': can_report_maintenance,
        'back_url': get_back_url(request, django_reverse('dashboard')),
    })


@require_POST
@require_admin
def release_vehicle_assignment(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    back_url = request.POST.get('back_url') or get_back_url(request, django_reverse('asset_detail', args=[pk]))

    if vehicle.asset:
        vehicle.asset.assigned_staff = None
        vehicle.asset.save()

    if vehicle.assigned_staff:
        vehicle.assigned_staff = None
        vehicle.save(update_fields=['assigned_staff'])

    messages.success(request, 'Vehicle assignment released successfully.')
    return redirect(back_url)


# ----------------------------
# Vehicle CRUD
# ----------------------------
@require_admin
def vehicle_create(request):
    if request.method == 'POST':
        form = VehicleForm(request.POST)
        back_url = request.POST.get('back_url') or get_back_url(request, django_reverse('dashboard'))
        if form.is_valid():
            form.save()
            messages.success(request, 'Asset added successfully.')
            return redirect('dashboard')
    else:
        form = VehicleForm()
        back_url = get_back_url(request, django_reverse('dashboard'))
    return render(request, 'asset_form.html', {'form': form, 'title': 'Add Asset', 'back_url': back_url})

@require_admin
def vehicle_update(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    if request.method == 'POST':
        form = VehicleForm(request.POST, instance=vehicle)
        back_url = request.POST.get('back_url') or get_back_url(request, django_reverse('asset_detail', args=[pk]))
        if form.is_valid():
            form.save()
            messages.success(request, 'Asset updated successfully.')
            return redirect('asset_detail', pk=pk)
    else:
        form = VehicleForm(instance=vehicle)
        back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('asset_detail', args=[pk]))
    return render(request, 'asset_form.html', {'form': form, 'title': 'Edit Asset', 'back_url': back_url})

@require_admin
def vehicle_update_type(request, pk):
    """Update only the asset type via modal quick edit"""
    vehicle = get_object_or_404(Vehicle, pk=pk)
    if request.method == 'POST':
        vehicle_type = request.POST.get('vehicle_type')
        if vehicle_type in dict(Vehicle.VEHICLE_TYPE_CHOICES):
            vehicle.vehicle_type = vehicle_type
            vehicle.save()
            messages.success(request, f'Asset type updated to {vehicle.get_vehicle_type_display()}.')
            log_audit(request.user, 'update', 'vehicle', vehicle, f"Updated asset type to {vehicle.get_vehicle_type_display()}", get_client_ip(request))
    return redirect('asset_detail', pk=pk)

@require_admin
def vehicle_delete(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    if request.method == 'POST':
        vehicle.delete()
        messages.success(request, 'Asset deleted successfully.')
        return redirect('dashboard')
    back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('asset_detail', args=[pk]))
    return render(request, 'asset_confirm_delete.html', {'vehicle': vehicle, 'back_url': back_url})


# ----------------------------
# Maintenance CRUD
# ----------------------------
@login_required
def maintenance_create(request, vehicle_pk):
    vehicle = get_object_or_404(Vehicle, pk=vehicle_pk)
    current_role = get_user_role(request.user)
    staff_profile = getattr(request.user, 'staff_profile', None)

    if current_role in ['staff', 'driver']:
        if not staff_profile or (
            vehicle.assigned_staff != staff_profile and
            not _assigned_user_matches_current_user(vehicle, request.user)
        ):
            return HttpResponseForbidden('Access denied')

    elif current_role not in ['admin', 'manager']:
        return HttpResponseForbidden('Access denied')

    if request.method == 'POST':
        form = MaintenanceItemForm(request.POST)
        back_url = request.POST.get('back_url') or get_back_url(request, django_reverse('asset_detail', args=[vehicle_pk]))
        if form.is_valid():
            maintenance = form.save(commit=False)
            maintenance.vehicle = vehicle
            maintenance.save()
            return redirect('asset_detail', pk=vehicle_pk)
    else:
        form = MaintenanceItemForm()
        back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('asset_detail', args=[vehicle_pk]))
    return render(request, 'maintenance_form.html', {'form': form, 'vehicle': vehicle, 'title': 'Add Maintenance', 'back_url': back_url})

@require_manager
def maintenance_update(request, pk):
    maintenance = get_object_or_404(MaintenanceItem, pk=pk)
    if request.method == 'POST':
        form = MaintenanceItemForm(request.POST, instance=maintenance)
        back_url = request.POST.get('back_url') or get_back_url(request, django_reverse('asset_detail', args=[maintenance.vehicle.pk]))
        if form.is_valid():
            form.save()
            return redirect('asset_detail', pk=maintenance.vehicle.pk)
    else:
        form = MaintenanceItemForm(instance=maintenance)
        back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('asset_detail', args=[maintenance.vehicle.pk]))
    return render(request, 'maintenance_form.html', {'form': form, 'vehicle': maintenance.vehicle, 'title': 'Edit Maintenance', 'back_url': back_url})

@require_manager
def maintenance_delete(request, pk):
    maintenance = get_object_or_404(MaintenanceItem, pk=pk)
    vehicle_pk = maintenance.vehicle.pk
    if request.method == 'POST':
        maintenance.delete()
        return redirect('asset_detail', pk=vehicle_pk)
    back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('asset_detail', args=[vehicle_pk]))
    return render(request, 'maintenance_confirm_delete.html', {'maintenance': maintenance, 'back_url': back_url})



@login_required
def export_vehicles_excel(request):
    vehicles = Vehicle.objects.all().order_by('-updated_at')
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Vehicles'
    sheet.append([
        'Name', 'Make', 'Model', 'VIN', 'License Plate', 'Type', 'Status', 'Insurance Expiry',
        'Roadworthy Expiry', 'License Expiry', 'Hackney Permit', 'Created At', 'Updated At'
    ])
    for vehicle in vehicles:
        sheet.append([
            vehicle.name,
            vehicle.make or '',
            vehicle.model or '',
            vehicle.vin_number or '',
            vehicle.license_plate,
            vehicle.get_asset_type_display(),
            vehicle.get_status_display(),
            vehicle.insurance_expiry or '',
            vehicle.roadworthy_expiry or '',
            vehicle.license_expiry or '',
            vehicle.hackney_permit or '',
            vehicle.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            vehicle.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
        ])
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="vehicles_export.xlsx"'
    workbook.save(response)
    return response


@login_required
def export_vehicles_csv(request):
    vehicles = Vehicle.objects.all().order_by('-updated_at')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="vehicles_export.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'Name', 'Make', 'Model', 'VIN', 'License Plate', 'Type', 'Status', 'Insurance Expiry',
        'Roadworthy Expiry', 'License Expiry', 'Hackney Permit', 'Created At', 'Updated At'
    ])
    for vehicle in vehicles:
        writer.writerow([
            vehicle.name,
            vehicle.make or '',
            vehicle.model or '',
            vehicle.vin_number or '',
            vehicle.license_plate,
            vehicle.get_asset_type_display(),
            vehicle.get_status_display(),
            vehicle.insurance_expiry or '',
            vehicle.roadworthy_expiry or '',
            vehicle.license_expiry or '',
            vehicle.hackney_permit or '',
            vehicle.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            vehicle.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
        ])
    return response


@login_required
def export_equipment_csv(request):
    """Export equipment to CSV with optional filtering."""
    # Get filter parameters from request
    search_query = request.GET.get('search', '')
    status_filter = request.GET.getlist('status')
    equipment_type_filter = request.GET.get('equipment_type', '')
    subsidiary_filter = request.GET.get('subsidiary', '')
    regional_office_filter = request.GET.get('regional_office', '')
    assignment_status_filter = request.GET.get('assignment_status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    cost_min = request.GET.get('cost_min', '')
    cost_max = request.GET.get('cost_max', '')
    age_filter = request.GET.get('age', '')
    warranty_status = request.GET.get('warranty_status', '')

    # Start with base queryset
    equipment_list = OfficeEquipment.objects.all().order_by('-updated_at')

    # Apply the same filters as equipment_list view
    if search_query:
        search_terms = search_query.split()
        search_query_obj = Q()
        for term in search_terms:
            search_query_obj |= (
                Q(name__icontains=term) |
                Q(serial_number__icontains=term) |
                Q(tag_number__icontains=term) |
                Q(assigned_user__icontains=term) |
                Q(description__icontains=term) |
                Q(remarks__icontains=term) |
                Q(location__icontains=term)
            )
        equipment_list = equipment_list.filter(search_query_obj)

    # Apply other filters
    if status_filter:
        equipment_list = equipment_list.filter(status__in=status_filter)
    if equipment_type_filter:
        equipment_list = equipment_list.filter(equipment_type=equipment_type_filter)
    if subsidiary_filter:
        equipment_list = equipment_list.filter(subsidiary=subsidiary_filter)
    if regional_office_filter:
        equipment_list = equipment_list.filter(regional_office=regional_office_filter)

    if assignment_status_filter == 'assigned':
        equipment_list = equipment_list.exclude(Q(assigned_user__isnull=True) | Q(assigned_user=''))
    elif assignment_status_filter == 'unassigned':
        equipment_list = equipment_list.filter(Q(assigned_user__isnull=True) | Q(assigned_user=''))

    # Date range filters
    if date_from:
        try:
            from_date = timezone.datetime.strptime(date_from, '%Y-%m-%d').date()
            equipment_list = equipment_list.filter(created_at__date__gte=from_date)
        except ValueError:
            pass

    if date_to:
        try:
            to_date = timezone.datetime.strptime(date_to, '%Y-%m-%d').date()
            equipment_list = equipment_list.filter(created_at__date__lte=to_date)
        except ValueError:
            pass

    # Cost range filters
    if cost_min:
        try:
            min_cost = float(cost_min)
            equipment_list = equipment_list.filter(cost__gte=min_cost)
        except ValueError:
            pass

    if cost_max:
        try:
            max_cost = float(cost_max)
            equipment_list = equipment_list.filter(cost__lte=max_cost)
        except ValueError:
            pass

    # Age and warranty filters
    current_year = timezone.now().year
    today = timezone.now().date()

    if age_filter:
        if age_filter == '0':
            equipment_list = equipment_list.filter(purchase_date__year=current_year)
        elif age_filter in ['1', '2', '3', '4']:
            equipment_list = equipment_list.filter(purchase_date__year=current_year - int(age_filter))
        elif age_filter == '5+':
            equipment_list = equipment_list.filter(purchase_date__year__lte=current_year - 5)

    if warranty_status:
        if warranty_status == 'expired':
            equipment_list = equipment_list.filter(warranty_expiry__lt=today)
        elif warranty_status == 'expiring':
            thirty_days_from_now = today + timedelta(days=30)
            equipment_list = equipment_list.filter(
                warranty_expiry__gte=today,
                warranty_expiry__lte=thirty_days_from_now
            )
        elif warranty_status == 'active':
            equipment_list = equipment_list.filter(warranty_expiry__gt=today + timedelta(days=30))

    # Create filename with filter info
    filter_parts = []
    if search_query:
        filter_parts.append(f"search-{search_query.replace(' ', '_')}")
    if equipment_type_filter:
        filter_parts.append(f"type-{equipment_type_filter}")
    if subsidiary_filter:
        filter_parts.append(f"subsidiary-{subsidiary_filter}")
    if regional_office_filter:
        filter_parts.append(f"office-{regional_office_filter.replace(' ', '_')}")

    filter_suffix = "_".join(filter_parts) if filter_parts else "all"
    filename = f"equipment_export_{filter_suffix}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        'Name', 'Type', 'Status', 'Subsidiary', 'Regional Office', 'Location',
        'Purchase Date', 'Warranty Expiry', 'Cost', 'Serial Number', 'Tag Number',
        'Assigned User', 'Year of Purchase', 'Quantity', 'Remarks', 'Description',
        'Created At', 'Updated At'
    ])

    for equipment in equipment_list:
        writer.writerow([
            equipment.name,
            equipment.get_equipment_type_display(),
            equipment.status.title(),
            equipment.subsidiary or '',
            equipment.regional_office or '',
            equipment.location or '',
            equipment.purchase_date or '',
            equipment.warranty_expiry or '',
            equipment.cost or '',
            equipment.serial_number or '',
            equipment.tag_number or '',
            equipment.assigned_user or '',
            (equipment.purchase_date.year if equipment.purchase_date else ''),
            equipment.quantity or '',
            equipment.remarks or '',
            equipment.description or '',
            equipment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            equipment.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
        ])

    return response


@login_required
def export_equipment_excel(request):
    """Export equipment to Excel with optional filtering."""
    # Use the same filtering logic as CSV export
    search_query = request.GET.get('search', '')
    status_filter = request.GET.getlist('status')
    equipment_type_filter = request.GET.get('equipment_type', '')
    subsidiary_filter = request.GET.get('subsidiary', '')
    regional_office_filter = request.GET.get('regional_office', '')
    assignment_status_filter = request.GET.get('assignment_status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    cost_min = request.GET.get('cost_min', '')
    cost_max = request.GET.get('cost_max', '')
    age_filter = request.GET.get('age', '')
    warranty_status = request.GET.get('warranty_status', '')

    equipment_list = OfficeEquipment.objects.all().order_by('-updated_at')

    # Apply the same filters as equipment_list view
    if search_query:
        search_terms = search_query.split()
        search_query_obj = Q()
        for term in search_terms:
            search_query_obj |= (
                Q(name__icontains=term) |
                Q(serial_number__icontains=term) |
                Q(tag_number__icontains=term) |
                Q(assigned_user__icontains=term) |
                Q(description__icontains=term) |
                Q(remarks__icontains=term) |
                Q(location__icontains=term)
            )
        equipment_list = equipment_list.filter(search_query_obj)

    # Apply other filters (same as CSV export)
    if status_filter:
        equipment_list = equipment_list.filter(status__in=status_filter)
    if equipment_type_filter:
        equipment_list = equipment_list.filter(equipment_type=equipment_type_filter)
    if subsidiary_filter:
        equipment_list = equipment_list.filter(subsidiary=subsidiary_filter)
    if regional_office_filter:
        equipment_list = equipment_list.filter(regional_office=regional_office_filter)

    if assignment_status_filter == 'assigned':
        equipment_list = equipment_list.exclude(Q(assigned_user__isnull=True) | Q(assigned_user=''))
    elif assignment_status_filter == 'unassigned':
        equipment_list = equipment_list.filter(Q(assigned_user__isnull=True) | Q(assigned_user=''))

    # Date, cost, age, and warranty filters (same as CSV)
    if date_from:
        try:
            from_date = timezone.datetime.strptime(date_from, '%Y-%m-%d').date()
            equipment_list = equipment_list.filter(created_at__date__gte=from_date)
        except ValueError:
            pass

    if date_to:
        try:
            to_date = timezone.datetime.strptime(date_to, '%Y-%m-%d').date()
            equipment_list = equipment_list.filter(created_at__date__lte=to_date)
        except ValueError:
            pass

    if cost_min:
        try:
            min_cost = float(cost_min)
            equipment_list = equipment_list.filter(cost__gte=min_cost)
        except ValueError:
            pass

    if cost_max:
        try:
            max_cost = float(cost_max)
            equipment_list = equipment_list.filter(cost__lte=max_cost)
        except ValueError:
            pass

    current_year = timezone.now().year
    today = timezone.now().date()

    if age_filter:
        if age_filter == '0':
            equipment_list = equipment_list.filter(purchase_date__year=current_year)
        elif age_filter in ['1', '2', '3', '4']:
            equipment_list = equipment_list.filter(purchase_date__year=current_year - int(age_filter))
        elif age_filter == '5+':
            equipment_list = equipment_list.filter(purchase_date__year__lte=current_year - 5)

    if warranty_status:
        if warranty_status == 'expired':
            equipment_list = equipment_list.filter(warranty_expiry__lt=today)
        elif warranty_status == 'expiring':
            thirty_days_from_now = today + timedelta(days=30)
            equipment_list = equipment_list.filter(
                warranty_expiry__gte=today,
                warranty_expiry__lte=thirty_days_from_now
            )
        elif warranty_status == 'active':
            equipment_list = equipment_list.filter(warranty_expiry__gt=today + timedelta(days=30))

    # Create filename with filter info
    filter_parts = []
    if search_query:
        filter_parts.append(f"search-{search_query.replace(' ', '_')}")
    if equipment_type_filter:
        filter_parts.append(f"type-{equipment_type_filter}")
    if subsidiary_filter:
        filter_parts.append(f"subsidiary-{subsidiary_filter}")
    if regional_office_filter:
        filter_parts.append(f"office-{regional_office_filter.replace(' ', '_')}")

    filter_suffix = "_".join(filter_parts) if filter_parts else "all"
    filename = f"equipment_export_{filter_suffix}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Office Equipment'

    # Add headers
    headers = [
        'Name', 'Type', 'Status', 'Subsidiary', 'Regional Office', 'Location',
        'Purchase Date', 'Warranty Expiry', 'Cost', 'Serial Number', 'Tag Number',
        'Assigned User', 'Year of Purchase', 'Quantity', 'Remarks', 'Description',
        'Created At', 'Updated At'
    ]
    sheet.append(headers)

    # Add data
    for equipment in equipment_list:
        sheet.append([
            equipment.name,
            equipment.get_equipment_type_display(),
            equipment.status.title(),
            equipment.subsidiary or '',
            equipment.regional_office or '',
            equipment.location or '',
            equipment.purchase_date.strftime('%Y-%m-%d') if equipment.purchase_date else '',
            equipment.warranty_expiry.strftime('%Y-%m-%d') if equipment.warranty_expiry else '',
            equipment.cost or '',
            equipment.serial_number or '',
            equipment.tag_number or '',
            equipment.assigned_user or '',
            (equipment.purchase_date.year if equipment.purchase_date else ''),
            equipment.quantity or '',
            equipment.remarks or '',
            equipment.description or '',
            equipment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            equipment.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
        ])

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    workbook.save(response)
    return response


@require_admin
def equipment_create(request):
    if request.method == 'POST':
        form = OfficeEquipmentForm(request.POST)
        back_url = request.POST.get('back_url') or get_back_url(request, django_reverse('equipment_list'))
        if form.is_valid():
            form.save()
            return redirect('equipment_list')
    else:
        form = OfficeEquipmentForm()
        back_url = get_back_url(request, django_reverse('equipment_list'))

    return render(request, 'equipment_form.html', {
        'form': form,
        'title': 'Add Equipment',
        'back_url': back_url
    })


@require_admin
def equipment_update(request, pk):
    equipment = get_object_or_404(OfficeEquipment, pk=pk)

    if request.method == 'POST':
        form = OfficeEquipmentForm(request.POST, instance=equipment)
        back_url = request.POST.get('back_url') or get_back_url(request, django_reverse('equipment_detail', args=[pk]))
        if form.is_valid():
            form.save()
            return redirect('equipment_detail', pk=pk)
    else:
        form = OfficeEquipmentForm(instance=equipment)
        back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('equipment_detail', args=[pk]))

    return render(request, 'equipment_form.html', {
        'form': form,
        'title': 'Edit Equipment',
        'back_url': back_url
    })


@require_admin
def equipment_delete(request, pk):
    equipment = get_object_or_404(OfficeEquipment, pk=pk)
    
    if request.method == 'POST':
        equipment.delete()
        return redirect('equipment_list')
    back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('equipment_detail', args=[pk]))
    return render(request, 'equipment_confirm_delete.html', {'equipment': equipment, 'back_url': back_url})


@login_required
def equipment_maintenance_create(request, equipment_pk):
    equipment = get_object_or_404(OfficeEquipment, pk=equipment_pk)
    current_role = get_user_role(request.user)
    staff_profile = getattr(request.user, 'staff_profile', None)

    if current_role in ['staff', 'driver']:
        if not staff_profile or (
            equipment.assigned_staff != staff_profile and
            not _assigned_user_matches_current_user(equipment, request.user)
        ):
            return HttpResponseForbidden('Access denied')
    elif current_role not in ['admin', 'manager']:
        return HttpResponseForbidden('Access denied')

    if request.method == 'POST':
        form = OfficeEquipmentMaintenanceForm(request.POST)
        back_url = request.POST.get('back_url') or get_back_url(request, django_reverse('equipment_detail', args=[equipment_pk]))
        if form.is_valid():
            maintenance = form.save(commit=False)
            maintenance.equipment = equipment
            maintenance.save()
            return redirect('equipment_detail', pk=equipment_pk)
    else:
        form = OfficeEquipmentMaintenanceForm()
        back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('equipment_detail', args=[equipment_pk]))

    return render(request, 'equipment_maintenance_form.html', {'form': form, 'equipment': equipment, 'title': 'Add Maintenance', 'back_url': back_url})

@require_manager
def equipment_maintenance_update(request, pk):
    maintenance = get_object_or_404(OfficeEquipmentMaintenance, pk=pk)
    if request.method == 'POST':
        form = OfficeEquipmentMaintenanceForm(request.POST, instance=maintenance)
        back_url = request.POST.get('back_url') or get_back_url(request, django_reverse('equipment_detail', args=[maintenance.equipment.pk]))
        if form.is_valid():
            form.save()
            return redirect('equipment_detail', pk=maintenance.equipment.pk)
    else:
        form = OfficeEquipmentMaintenanceForm(instance=maintenance)
        back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('equipment_detail', args=[maintenance.equipment.pk]))
    return render(request, 'equipment_maintenance_form.html', {'form': form, 'equipment': maintenance.equipment, 'title': 'Edit Maintenance', 'back_url': back_url})

@require_manager
def equipment_maintenance_delete(request, pk):
    maintenance = get_object_or_404(OfficeEquipmentMaintenance, pk=pk)
    
    if request.method == 'POST':
        maintenance.delete()
        return redirect('equipment_detail', pk=maintenance.equipment.pk)
    back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('equipment_detail', args=[maintenance.equipment.pk]))
    return render(request, 'equipment_maintenance_confirm_delete.html', {'maintenance': maintenance, 'back_url': back_url})


# ========================
# BULK UPLOAD FEATURES
# ========================

@require_admin
def bulk_upload_assets(request):
    """Handle bulk asset upload from CSV, Excel, or Word files with validation."""
    from .bulk_utils import parse_bulk_upload_csv, parse_excel_vehicles, parse_docx_vehicles, validate_vehicle_row
    
    if request.method == 'POST':
        file_obj = request.FILES.get('csv_file')
        excel_file = request.FILES.get('excel_file')
        docx_file = request.FILES.get('docx_file')
        
        # Validate file size
        selected_file = file_obj or excel_file or docx_file
        if selected_file:
            file_size_mb = selected_file.size / (1024 * 1024)
            if file_size_mb > settings.FILE_UPLOAD_MAX_SIZE_MB:
                messages.error(request, f"File too large. Maximum size: {settings.FILE_UPLOAD_MAX_SIZE_MB}MB")
                return render(request, 'bulk_upload_assets.html')
            
            # Parse file based on type
            if file_obj:
                rows, error = parse_bulk_upload_csv(file_obj)
            elif excel_file:
                rows, error = parse_excel_vehicles(excel_file)
            elif docx_file:
                rows, error = parse_docx_vehicles(docx_file)
            else:
                error = "No file provided"
            
            if error:
                messages.error(request, error)
                return render(request, 'bulk_upload_assets.html')
            
            try:
                created = 0
                failed = 0
                errors_log = []
                
                # Use transaction for bulk import
                with transaction.atomic():
                    for idx, row in enumerate(rows, 1):
                        # Validate row
                        validation_errors = validate_vehicle_row(row)
                        if validation_errors:
                            failed += 1
                            error_msg = f"Row {idx}: {', '.join(validation_errors.values())}"
                            errors_log.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Prepare vehicle data
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
                        
                        # Check for duplicates
                        duplicate_plate = vehicle_data['license_plate'] and Vehicle.objects.filter(license_plate=vehicle_data['license_plate']).exists()
                        duplicate_vin = vehicle_data['vin_number'] and Vehicle.objects.filter(vin_number=vehicle_data['vin_number']).exists()

                        if duplicate_plate or duplicate_vin:
                            failed += 1
                            if duplicate_plate:
                                error_msg = f"Row {idx}: Vehicle with plate {vehicle_data['license_plate']} already exists"
                            else:
                                error_msg = f"Row {idx}: Vehicle with VIN {vehicle_data['vin_number']} already exists"
                            errors_log.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        try:
                            Vehicle.objects.create(**vehicle_data)
                            created += 1
                        except Exception as e:
                            failed += 1
                            error_msg = f"Row {idx}: Error creating vehicle - {str(e)}"
                            errors_log.append(error_msg)
                            logger.error(error_msg)
                
                # Provide user feedback
                if created > 0:
                    messages.success(request, f"Successfully imported {created} asset(s).")
                    log_audit(request.user, 'bulk_create', 'assets', description=f"Bulk uploaded {created} assets")
                
                if failed > 0:
                    messages.warning(request, f"{failed} row(s) failed. Check logs for details.")
                
                if created == 0 and failed > 0:
                    messages.error(request, "No assets were imported.")
                
            except Exception as e:
                logger.error(f"Error processing vehicle bulk upload: {e}")
                messages.error(request, f"Error processing file: {str(e)}")
            
            return redirect('dashboard')

    return render(request, 'bulk_upload_assets.html')

@require_admin
def bulk_upload_equipment(request):
    """Handle bulk equipment upload from CSV, Excel with validation and transactions."""
    from .bulk_utils import parse_bulk_upload_csv, parse_Excel_equipment, validate_equipment_row
    
    if request.method == 'POST':
        file_obj = request.FILES.get('csv_file')
        excel_file = request.FILES.get('excel_file')
        
        # Validate file size
        selected_file = file_obj or excel_file
        if selected_file:
            file_size_mb = selected_file.size / (1024 * 1024)
            if file_size_mb > settings.FILE_UPLOAD_MAX_SIZE_MB:
                messages.error(request, f"File too large. Maximum size: {settings.FILE_UPLOAD_MAX_SIZE_MB}MB")
                return render(request, 'bulk_upload_equipment.html')
        
        rows = None
        error = None
        
        try:
            # Parse file based on type
            if file_obj:
                rows, error = parse_bulk_upload_csv(file_obj)
            elif excel_file:
                rows, error = parse_Excel_equipment(excel_file)
            else:
                error = "No file provided"
            
            if error:
                messages.error(request, error)
                return render(request, 'bulk_upload_equipment.html')
            
            created = 0
            failed = 0
            errors_log = []
            
            # Use transaction for bulk import
            with transaction.atomic():
                for idx, row in enumerate(rows, 1):
                    # Validate row
                    validation_errors = validate_equipment_row(row)
                    if validation_errors:
                        failed += 1
                        error_msg = f"Row {idx}: {', '.join(validation_errors.values())}"
                        errors_log.append(error_msg)
                        logger.warning(error_msg)
                        continue
                    
                    # Prepare equipment data
                    # Convert a provided year_of_purchase into a purchase_date (Jan 1 of that year) when purchase_date missing
                    purchase_date = row.get('purchase_date') or None
                    yop = row.get('year_of_purchase') or None
                    if not purchase_date and yop:
                        try:
                            year_int = int(yop)
                            purchase_date = f"{year_int}-01-01"
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
                    except Exception as e:
                        failed += 1
                        error_msg = f"Row {idx}: Error creating equipment - {str(e)}"
                        errors_log.append(error_msg)
                        logger.error(error_msg)
            
            # Provide user feedback
            if created > 0:
                messages.success(request, f"Successfully imported {created} equipment item(s).")
                log_audit(request.user, 'bulk_create', 'office_equipment', description=f"Bulk uploaded {created} equipment")
            
            if failed > 0:
                messages.warning(request, f"{failed} row(s) failed. Check logs for details.")
            
            if created == 0 and failed > 0:
                messages.error(request, "No equipment was imported.")
            
            return redirect('equipment_list')
        
        except Exception as e:
            logger.error(f"Error processing equipment bulk upload: {e}")
            messages.error(request, f"Error processing file: {str(e)}")
    
    return render(request, 'bulk_upload_equipment.html')


@login_required
def equipment_transfer(request, pk):
    """Handle equipment transfer/handover to another staff member"""
    equipment = get_object_or_404(OfficeEquipment, pk=pk)
    if request.method == 'POST':
        form = EquipmentTransferForm(request.POST)
        back_url = request.POST.get('back_url') or get_back_url(request, django_reverse('equipment_detail', args=[pk]))
        if form.is_valid():
            from .models import EquipmentTransfer
            
            # Create the transfer record
            transfer = EquipmentTransfer(
                equipment=equipment,
                transferred_from=equipment.assigned_user or 'Unassigned',
                transferred_from_department='',
                transferred_to=form.cleaned_data['transferred_to'],
                transferred_to_department=form.cleaned_data.get('transferred_to_department', ''),
                transferred_to_email=form.cleaned_data.get('transferred_to_email', ''),
                reason=form.cleaned_data.get('reason', ''),
                notes=form.cleaned_data.get('notes', ''),
                recorded_by=request.user
            )
            transfer.save()
            
            # Update the equipment's assigned user
            equipment.assigned_user = form.cleaned_data['transferred_to']
            equipment.save()
            
            # Log the action
            log_audit(request.user, 'update', 'OfficeEquipment', pk, 
                     description=f"Transferred {equipment.name} to {form.cleaned_data['transferred_to']}")
            
            messages.success(request, f"Equipment '{equipment.name}' has been successfully transferred to {form.cleaned_data['transferred_to']}.")
            return redirect('equipment_detail', pk=pk)
    else:
        form = EquipmentTransferForm()
        back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('equipment_detail', args=[pk]))
    
    return render(request, 'equipment_transfer.html', {
        'form': form,
        'equipment': equipment,
        'current_user': equipment.assigned_user or 'Unassigned',
        'back_url': back_url
    })


@login_required
def equipment_transfer_history(request, pk):
    """Display transfer history for an equipment"""
    from .models import EquipmentTransfer
    
    equipment = get_object_or_404(OfficeEquipment, pk=pk)
    transfers = EquipmentTransfer.objects.filter(equipment=equipment).order_by('-transfer_date')
    
    # Pagination
    page_num = request.GET.get('page', 1)
    paginator = Paginator(transfers, 20)
    try:
        page_obj = paginator.page(page_num)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)
    
    back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('equipment_detail', args=[pk]))
    return render(request, 'equipment_transfer_history.html', {
        'equipment': equipment,
        'transfers': page_obj,
        'total_transfers': transfers.count(),
        'back_url': back_url
    })


# ========================
# EQUIPMENT LIST VIEWS
# ========================

@login_required
def equipment_list(request):
    """Display all office equipment with advanced filtering and pagination."""
    search_query = request.GET.get('search', '')
    status_filter = request.GET.getlist('status')
    category_filter = request.GET.get('category', '')
    subsidiary_filter = request.GET.get('subsidiary', '')
    regional_office_filter = request.GET.get('regional_office', '')
    equipment_type_filter = request.GET.get('equipment_type', category_filter)
    assignment_status_filter = request.GET.get('assignment_status', '')
    sort_by = request.GET.get('sort_by', 'updated_at')
    sort_dir = request.GET.get('sort_dir', 'desc')
    page_num = request.GET.get('page', 1)

    # Department scoping: default to manager's department when applicable
    department_filter = request.GET.get('department', '')
    try:
        if not department_filter and get_user_role(request.user) == 'manager' and hasattr(request.user, 'role'):
            dept = request.user.role.department
            if dept:
                department_filter = dept
    except Exception:
        department_filter = department_filter

    # Advanced filters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    cost_min = request.GET.get('cost_min', '')
    cost_max = request.GET.get('cost_max', '')
    age_filter = request.GET.get('age', '')  # 0-5+ years
    warranty_status = request.GET.get('warranty_status', '')  # expired, active, expiring

    try:
        page_size = int(request.GET.get('page_size', 25))
    except (TypeError, ValueError):
        page_size = 25
    if page_size not in [10, 25, 50]:
        page_size = 25

    equipments = OfficeEquipment.objects.all()
    current_role = get_user_role(request.user)
    staff_profile = getattr(request.user, 'staff_profile', None)
    if current_role in ['staff', 'driver'] and staff_profile is not None:
        equipments = equipments.filter(assigned_staff=staff_profile)
    elif department_filter:
        equipments = equipments.filter(assigned_staff__department=department_filter)

    # Enhanced search with multiple fields and optimization
    if search_query:
        search_terms = search_query.split()
        search_query_obj = Q()
        for term in search_terms:
            search_query_obj |= (
                Q(name__icontains=term) |
                Q(serial_number__icontains=term) |
                Q(tag_number__icontains=term) |
                Q(assigned_user__icontains=term) |
                Q(description__icontains=term) |
                Q(remarks__icontains=term) |
                Q(location__icontains=term)
            )
        equipments = equipments.filter(search_query_obj)

    # Date range filters
    if date_from:
        try:
            from_date = timezone.datetime.strptime(date_from, '%Y-%m-%d').date()
            equipments = equipments.filter(created_at__date__gte=from_date)
        except ValueError:
            pass

    if date_to:
        try:
            to_date = timezone.datetime.strptime(date_to, '%Y-%m-%d').date()
            equipments = equipments.filter(created_at__date__lte=to_date)
        except ValueError:
            pass

    # Cost range filters
    if cost_min:
        try:
            min_cost = float(cost_min)
            equipments = equipments.filter(cost__gte=min_cost)
        except ValueError:
            pass

    if cost_max:
        try:
            max_cost = float(cost_max)
            equipments = equipments.filter(cost__lte=max_cost)
        except ValueError:
            pass

    # Age filter
    current_year = timezone.now().year
    if age_filter:
        if age_filter == '0':  # This year
            equipments = equipments.filter(purchase_date__year=current_year)
        elif age_filter == '1':  # 1 year old
            equipments = equipments.filter(purchase_date__year=current_year - 1)
        elif age_filter == '2':  # 2 years old
            equipments = equipments.filter(purchase_date__year=current_year - 2)
        elif age_filter == '3':  # 3 years old
            equipments = equipments.filter(purchase_date__year=current_year - 3)
        elif age_filter == '4':  # 4 years old
            equipments = equipments.filter(purchase_date__year=current_year - 4)
        elif age_filter == '5+':  # 5+ years old
            equipments = equipments.filter(purchase_date__year__lte=current_year - 5)

    # Warranty status filter
    today = timezone.now().date()
    if warranty_status:
        if warranty_status == 'expired':
            equipments = equipments.filter(warranty_expiry__lt=today)
        elif warranty_status == 'expiring':
            thirty_days_from_now = today + timedelta(days=30)
            equipments = equipments.filter(
                warranty_expiry__gte=today,
                warranty_expiry__lte=thirty_days_from_now
            )
        elif warranty_status == 'active':
            equipments = equipments.filter(warranty_expiry__gt=today + timedelta(days=30))

    # Apply filters only once
    if status_filter:
        equipments = equipments.filter(status__in=status_filter)

    if equipment_type_filter:
        equipments = equipments.filter(equipment_type=equipment_type_filter)

    if subsidiary_filter:
        equipments = equipments.filter(subsidiary=subsidiary_filter)

    if regional_office_filter:
        equipments = equipments.filter(regional_office=regional_office_filter)

    if assignment_status_filter == 'assigned':
        equipments = equipments.exclude(Q(assigned_user__isnull=True) | Q(assigned_user=''))
    elif assignment_status_filter == 'unassigned':
        equipments = equipments.filter(Q(assigned_user__isnull=True) | Q(assigned_user=''))

    # Sorting
    if sort_by == 'name':
        equipments = equipments.order_by(f'{"-" if sort_dir == "desc" else ""}name')
    elif sort_by == 'type':
        equipments = equipments.order_by(f'{"-" if sort_dir == "desc" else ""}equipment_type')
    elif sort_by == 'status':
        equipments = equipments.order_by(f'{"-" if sort_dir == "desc" else ""}status')
    elif sort_by == 'subsidiary':
        equipments = equipments.order_by(f'{"-" if sort_dir == "desc" else ""}subsidiary')
    elif sort_by == 'location':
        equipments = equipments.order_by(f'{"-" if sort_dir == "desc" else ""}regional_office')
    else:
        equipments = equipments.order_by(f'{"-" if sort_dir == "desc" else ""}updated_at')

    # Pagination
    paginator = Paginator(equipments, page_size)
    try:
        page_obj = paginator.page(page_num)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # Stats
    total_equipments = equipments.count()
    active_count = equipments.filter(status='active').count()
    inactive_count = equipments.filter(status='inactive').count()
    damaged_count = equipments.filter(status='damaged').count()
    unassigned_count = equipments.filter(Q(assigned_user__isnull=True) | Q(assigned_user='')).count()
    regional_offices = [choice[0] for choice in OfficeEquipment.REGIONAL_OFFICE_CHOICES]
    regional_office_counts = {office: OfficeEquipment.objects.filter(regional_office=office).count() for office in regional_offices}
    equipment_types = OfficeEquipment.EQUIPMENT_TYPE_CHOICES
    subsidiaries = [choice[0] for choice in OfficeEquipment.SUBSIDIARY_CHOICES if choice[0]]

    # Filter options
    status_options = [
        ('active', f'Active ({active_count})'),
        ('inactive', f'Inactive ({inactive_count})'),
        ('damaged', f'Damaged ({damaged_count})'),
        ('pending_certification', 'Pending Certification'),
    ]

    category_options = [
        (choice[0], f'{choice[1]} ({equipments.filter(equipment_type=choice[0]).count()})')
        for choice in OfficeEquipment.EQUIPMENT_TYPE_CHOICES
    ]

    # Equipment type counts for cards (always show total counts, not filtered counts)
    equipment_type_counts = {
        choice[0]: OfficeEquipment.objects.filter(equipment_type=choice[0]).count()
        for choice in OfficeEquipment.EQUIPMENT_TYPE_CHOICES
    }

    subsidiary_options = [
        (choice[0], f'{choice[1]} ({equipments.filter(subsidiary=choice[0]).count()})')
        for choice in OfficeEquipment.SUBSIDIARY_CHOICES
    ]

    location_options = [
        (choice[0], f'{choice[1]} ({equipments.filter(regional_office=choice[0]).count()})')
        for choice in OfficeEquipment.REGIONAL_OFFICE_CHOICES
    ]

    return render(request, 'equipment_list.html', {
        'equipments': page_obj,
        'total_equipment': total_equipments,
        'total_equipments': total_equipments,
        'search_query': search_query,
        'status_filter': status_filter,
        'subsidiary_filter': subsidiary_filter,
        'regional_office_filter': regional_office_filter,
        'equipment_type_filter': equipment_type_filter,
        'assignment_status_filter': assignment_status_filter,
        'department_filter': department_filter,
        'sort_by': sort_by,
        'sort_dir': sort_dir,
        'page_size': page_size,
        'paginator': paginator,
        'page_obj': page_obj,
        'status_options': status_options,
        'category_options': category_options,
        'subsidiary_options': subsidiary_options,
        'regional_offices': regional_offices,
        'regional_office_counts': regional_office_counts,
        'equipment_types': equipment_types,
        'subsidiaries': subsidiaries,
        'active_count': active_count,
        'inactive_count': inactive_count,
        'damaged_count': damaged_count,
        'unassigned_count': unassigned_count,
        'equipment_type_counts': equipment_type_counts,
        # Advanced filter parameters
        'date_from': date_from,
        'date_to': date_to,
        'cost_min': cost_min,
        'cost_max': cost_max,
        'age_filter': age_filter,
        'warranty_status': warranty_status,
        # Age filter options
        'age_options': [
            ('', 'All Ages'),
            ('0', 'This Year'),
            ('1', '1 Year Old'),
            ('2', '2 Years Old'),
            ('3', '3 Years Old'),
            ('4', '4 Years Old'),
            ('5+', '5+ Years Old'),
        ],
        # Warranty status options
        'warranty_options': [
            ('', 'All Warranty Status'),
            ('active', 'Active Warranty'),
            ('expiring', 'Expiring Soon (30 days)'),
            ('expired', 'Expired Warranty'),
        ],
    })


@login_required
def equipment_abuja(request):
    """Display equipment for Abuja office."""
    return equipment_list_filtered(request, regional_office='Abuja', title='Abuja Equipment')


@login_required
def equipment_iteco(request):
    """Display equipment for ITECO subsidiary."""
    return equipment_list_filtered(request, subsidiary='ITECO', title='ITECO Equipment')


@login_required
def equipment_softworks(request):
    """Display equipment for Softworks subsidiary."""
    return equipment_list_filtered(request, subsidiary='Softworks', title='Softworks Equipment')


def equipment_list_filtered(request, **filters):
    """Helper function to display filtered equipment lists."""
    title = filters.pop('title', 'Equipment')
    search_query = request.GET.get('search', '')
    status_filter = request.GET.getlist('status')
    subsidiary_filter = request.GET.get('subsidiary', filters.get('subsidiary', ''))
    regional_office_filter = request.GET.get('regional_office', filters.get('regional_office', ''))
    category_filter = request.GET.get('category', '')
    equipment_type_filter = request.GET.get('equipment_type', category_filter)
    assignment_status_filter = request.GET.get('assignment_status', '')
    sort_by = request.GET.get('sort_by', 'updated_at')
    sort_dir = request.GET.get('sort_dir', 'desc')
    page_num = request.GET.get('page', 1)

    try:
        page_size = int(request.GET.get('page_size', 25))
    except (TypeError, ValueError):
        page_size = 25
    if page_size not in [10, 25, 50]:
        page_size = 25

    equipments = OfficeEquipment.objects.filter(**filters)

    # Apply additional filters
    if search_query:
        equipments = equipments.filter(
            Q(name__icontains=search_query) |
            Q(serial_number__icontains=search_query) |
            Q(tag_number__icontains=search_query) |
            Q(assigned_user__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    if status_filter:
        equipments = equipments.filter(status__in=status_filter)

    if equipment_type_filter:
        equipments = equipments.filter(equipment_type=equipment_type_filter)

    if assignment_status_filter == 'assigned':
        equipments = equipments.exclude(Q(assigned_user__isnull=True) | Q(assigned_user=''))
    elif assignment_status_filter == 'unassigned':
        equipments = equipments.filter(Q(assigned_user__isnull=True) | Q(assigned_user=''))

    # Sorting
    if sort_by == 'name':
        equipments = equipments.order_by(f'{"-" if sort_dir == "desc" else ""}name')
    elif sort_by == 'type':
        equipments = equipments.order_by(f'{"-" if sort_dir == "desc" else ""}equipment_type')
    elif sort_by == 'status':
        equipments = equipments.order_by(f'{"-" if sort_dir == "desc" else ""}status')
    else:
        equipments = equipments.order_by(f'{"-" if sort_dir == "desc" else ""}updated_at')

    # Pagination
    paginator = Paginator(equipments, page_size)
    try:
        page_obj = paginator.page(page_num)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # Stats
    total_equipments = equipments.count()
    active_count = equipments.filter(status='active').count()
    inactive_count = equipments.filter(status='inactive').count()
    damaged_count = equipments.filter(status='damaged').count()
    unassigned_count = equipments.filter(Q(assigned_user__isnull=True) | Q(assigned_user='')).count()
    regional_offices = [choice[0] for choice in OfficeEquipment.REGIONAL_OFFICE_CHOICES]
    regional_office_counts = {office: OfficeEquipment.objects.filter(regional_office=office).count() for office in regional_offices}
    equipment_types = OfficeEquipment.EQUIPMENT_TYPE_CHOICES
    subsidiaries = [choice[0] for choice in OfficeEquipment.SUBSIDIARY_CHOICES if choice[0]]

    # Filter options
    status_options = [
        ('active', f'Active ({active_count})'),
        ('inactive', f'Inactive ({inactive_count})'),
        ('damaged', f'Damaged ({damaged_count})'),
        ('pending_certification', 'Pending Certification'),
    ]

    category_options = [
        (choice[0], f'{choice[1]} ({equipments.filter(equipment_type=choice[0]).count()})')
        for choice in OfficeEquipment.EQUIPMENT_TYPE_CHOICES
    ]

    return render(request, 'equipment_list.html', {
        'equipments': page_obj,
        'total_equipment': total_equipments,
        'total_equipments': total_equipments,
        'title': title,
        'search_query': search_query,
        'status_filter': status_filter,
        'subsidiary_filter': subsidiary_filter,
        'regional_office_filter': regional_office_filter,
        'equipment_type_filter': equipment_type_filter,
        'assignment_status_filter': assignment_status_filter,
        'sort_by': sort_by,
        'sort_dir': sort_dir,
        'page_size': page_size,
        'paginator': paginator,
        'page_obj': page_obj,
        'status_options': status_options,
        'category_options': category_options,
        'regional_offices': regional_offices,
        'regional_office_counts': regional_office_counts,
        'equipment_types': equipment_types,
        'subsidiaries': subsidiaries,
        'active_count': active_count,
        'inactive_count': inactive_count,
        'damaged_count': damaged_count,
        'unassigned_count': unassigned_count,
        'is_filtered_view': True,
    })


@login_required
def equipment_detail(request, pk):
    equipment = get_object_or_404(OfficeEquipment, pk=pk)
    maintenance_records = equipment.maintenance_records.all()
    assignment_history = equipment.asset.assignments.all() if equipment.asset else []
    related_assets = equipment.asset.get_linked_assets() if equipment.asset else []
    if equipment.asset:
        asset_ids = [equipment.asset.pk] + list(related_assets.values_list('pk', flat=True))
        related_documents = CompanyDocument.objects.filter(
            Q(related_equipment=equipment) |
            Q(related_asset__in=asset_ids)
        ).distinct().order_by('-expiry_date')
    else:
        related_documents = CompanyDocument.objects.filter(
            related_equipment=equipment
        ).order_by('-expiry_date')

    current_role = get_user_role(request.user)
    staff_profile = getattr(request.user, 'staff_profile', None)
    can_report_maintenance = False
    if current_role in ['admin', 'manager']:
        can_report_maintenance = True
    elif staff_profile and equipment.assigned_staff == staff_profile:
        can_report_maintenance = True
    elif current_role in ['staff', 'driver'] and _assigned_user_matches_current_user(equipment, request.user):
        can_report_maintenance = True

    return render(request, 'equipment_detail.html', {
        'equipment': equipment,
        'maintenance_records': maintenance_records,
        'assignment_history': assignment_history,
        'related_assets': related_assets,
        'related_documents': related_documents,
        'can_report_maintenance': can_report_maintenance,
        'back_url': get_back_url(request, django_reverse('equipment_list'))
    })


@require_POST
@require_admin
def release_equipment_assignment(request, pk):
    equipment = get_object_or_404(OfficeEquipment, pk=pk)
    back_url = request.POST.get('back_url') or get_back_url(request, django_reverse('equipment_detail', args=[pk]))

    if equipment.asset:
        equipment.asset.assigned_staff = None
        equipment.asset.save()

    if equipment.assigned_staff:
        equipment.assigned_staff = None
        equipment.save(update_fields=['assigned_staff'])

    messages.success(request, 'Equipment assignment released successfully.')
    return redirect(back_url)


# ===== Company Documents Views =====

@login_required(login_url='login')
@require_manager
def company_documents_list(request):
    """List all company documents with filtering by status, type, scope, and search."""
    status_filter = request.GET.get('status', 'all')
    type_filter = request.GET.get('type', 'all')
    scope_filter = request.GET.get('scope', 'all')
    search_query = request.GET.get('search', '').strip()
    department_filter = request.GET.get('department', '')

    # Default to manager's department when applicable
    try:
        if not department_filter and get_user_role(request.user) == 'manager' and hasattr(request.user, 'role'):
            dept = request.user.role.department
            if dept:
                department_filter = dept
    except Exception:
        department_filter = department_filter

    documents = CompanyDocument.objects.all().order_by('-expiry_date')

    # If a department filter is active, scope documents to that department (responsible staff or related assets)
    if department_filter:
        documents = documents.filter(
            Q(responsible_staff__department=department_filter) |
            Q(related_asset__assigned_staff__department=department_filter) |
            Q(related_vehicle__assigned_staff__department=department_filter) |
            Q(related_equipment__assigned_staff__department=department_filter)
        ).distinct()

    if scope_filter == 'vehicle':
        documents = documents.filter(
            Q(related_vehicle__isnull=False) |
            Q(related_asset__asset_type='vehicle')
        )
    elif scope_filter == 'equipment':
        documents = documents.filter(
            Q(related_equipment__isnull=False) |
            Q(related_asset__asset_type='equipment')
        )
    elif scope_filter == 'company':
        documents = documents.filter(
            Q(related_vehicle__isnull=True),
            Q(related_equipment__isnull=True),
            Q(related_asset__isnull=True) | Q(related_asset__asset_type='other')
        )

    if search_query:
        documents = documents.filter(
            Q(name__icontains=search_query) |
            Q(document_number__icontains=search_query) |
            Q(issuing_authority__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(responsible_person__icontains=search_query) |
            Q(responsible_staff__staff_id__icontains=search_query) |
            Q(responsible_staff__first_name__icontains=search_query) |
            Q(responsible_staff__last_name__icontains=search_query) |
            Q(location__icontains=search_query) |
            Q(related_vehicle__name__icontains=search_query) |
            Q(related_vehicle__license_plate__icontains=search_query) |
            Q(related_equipment__name__icontains=search_query) |
            Q(related_equipment__serial_number__icontains=search_query) |
            Q(related_asset__name__icontains=search_query) |
            Q(related_asset__asset_type__icontains=search_query) |
            Q(related_asset__description__icontains=search_query)
        )

    if type_filter != 'all':
        documents = documents.filter(document_type=type_filter)

    if status_filter in ('expired', 'expiring', 'safe'):
        documents = [document for document in documents if document.get_status() == status_filter]
    else:
        documents = list(documents)

    documents_all = list(CompanyDocument.objects.all())
    expired_count = sum(1 for document in documents_all if document.get_status() == 'expired')
    expiring_count = sum(1 for document in documents_all if document.get_status() == 'expiring')
    safe_count = sum(1 for document in documents_all if document.get_status() == 'safe')

    total_document_count = len(documents_all)
    # Compute vehicle-related asset ids: direct vehicle assets and assets linked to them
    vehicle_asset_qs = Asset.objects.filter(asset_type='vehicle')
    vehicle_asset_ids = set(vehicle_asset_qs.values_list('pk', flat=True))

    # Include any assets linked to vehicle assets via AssetRelationship (both directions)
    linked_from = AssetRelationship.objects.filter(from_asset__in=vehicle_asset_qs).values_list('to_asset', flat=True)
    linked_to = AssetRelationship.objects.filter(to_asset__in=vehicle_asset_qs).values_list('from_asset', flat=True)
    for aid in list(linked_from) + list(linked_to):
        if aid:
            vehicle_asset_ids.add(aid)

    vehicle_document_count = CompanyDocument.objects.filter(
        Q(related_vehicle__isnull=False) |
        Q(related_asset__in=vehicle_asset_ids) |
        Q(related_asset__asset_type='vehicle')
    ).distinct().count()

    equipment_document_count = CompanyDocument.objects.filter(
        Q(related_equipment__isnull=False) | Q(related_asset__asset_type='equipment')
    ).distinct().count()

    company_document_count = CompanyDocument.objects.filter(
        Q(related_vehicle__isnull=True),
        Q(related_equipment__isnull=True),
        Q(related_asset__isnull=True) | Q(related_asset__asset_type='other')
    ).count()

    paginator = Paginator(documents, 20)
    page = request.GET.get('page')
    try:
        documents_page = paginator.page(page)
    except PageNotAnInteger:
        documents_page = paginator.page(1)
    except EmptyPage:
        documents_page = paginator.page(paginator.num_pages)

    preserved_params = request.GET.copy()
    preserved_params.pop('page', None)
    preserved_query_string = preserved_params.urlencode()

    status_params = request.GET.copy()
    status_params.pop('page', None)
    status_params.pop('status', None)
    status_query_string = status_params.urlencode()

    scope_params = request.GET.copy()
    scope_params.pop('page', None)
    scope_params.pop('scope', None)
    scope_query_string = scope_params.urlencode()

    context = {
        'documents': documents_page,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'scope_filter': scope_filter,
        'search_query': search_query,
        'total_count': total_document_count,
        'vehicle_document_count': vehicle_document_count,
        'equipment_document_count': equipment_document_count,
        'company_document_count': company_document_count,
        'expired_count': expired_count,
        'expiring_count': expiring_count,
        'safe_count': safe_count,
        'document_type_choices': CompanyDocument.DOCUMENT_TYPE_CHOICES,
        'can_create_company_document': is_admin(request.user),
        'preserved_query_string': preserved_query_string,
        'status_query_string': status_query_string,
        'scope_query_string': scope_query_string,
    }

    log_audit(request.user, 'view', 'companydocument', description='Viewed company documents list')
    return render(request, 'company_documents/list.html', context)


@login_required(login_url='login')
def company_documents_counts(request):
    """Return JSON payload of document counts used by frontend to refresh counts via AJAX."""
    from .models import Asset, AssetRelationship

    documents_all = list(CompanyDocument.objects.all())
    expired_count = sum(1 for document in documents_all if document.get_status() == 'expired')
    expiring_count = sum(1 for document in documents_all if document.get_status() == 'expiring')
    safe_count = sum(1 for document in documents_all if document.get_status() == 'safe')

    total_document_count = len(documents_all)

    vehicle_asset_qs = Asset.objects.filter(asset_type='vehicle')
    vehicle_asset_ids = set(vehicle_asset_qs.values_list('pk', flat=True))
    linked_from = AssetRelationship.objects.filter(from_asset__in=vehicle_asset_qs).values_list('to_asset', flat=True)
    linked_to = AssetRelationship.objects.filter(to_asset__in=vehicle_asset_qs).values_list('from_asset', flat=True)
    for aid in list(linked_from) + list(linked_to):
        if aid:
            vehicle_asset_ids.add(aid)

    vehicle_document_count = CompanyDocument.objects.filter(
        Q(related_vehicle__isnull=False) |
        Q(related_asset__in=vehicle_asset_ids) |
        Q(related_asset__asset_type='vehicle')
    ).distinct().count()

    equipment_document_count = CompanyDocument.objects.filter(
        Q(related_equipment__isnull=False) | Q(related_asset__asset_type='equipment')
    ).distinct().count()

    company_document_count = CompanyDocument.objects.filter(
        Q(related_vehicle__isnull=True),
        Q(related_equipment__isnull=True),
        Q(related_asset__isnull=True) | Q(related_asset__asset_type='other')
    ).count()

    payload = {
        'expired_count': expired_count,
        'expiring_count': expiring_count,
        'safe_count': safe_count,
        'vehicle_document_count': vehicle_document_count,
        'equipment_document_count': equipment_document_count,
        'company_document_count': company_document_count,
        'total_document_count': total_document_count,
    }
    return JsonResponse(payload)


@login_required
def my_assets(request):
    """Shortcut for users (drivers/staff) to view assets assigned to them.

    Redirects to the dashboard with the `assigned_staff` query parameter
    when the current user is linked to a `StaffMember` record.
    """
    try:
        staff = request.user.staff_profile
        if staff:
            return redirect(django_reverse('dashboard') + f'?assigned_staff={staff.pk}')
    except Exception:
        pass
    return redirect('dashboard')


@login_required
def _my_assets_counts_removed_for_prd(request):
    # Previously returned per-user asset counts for the 'My Assets' UI.
    # Removed per PRD; kept as a no-op placeholder to avoid accidental imports.
    from django.http import JsonResponse
    return JsonResponse({'vehicles': 0, 'equipment': 0, 'documents': 0, 'total': 0})


@login_required(login_url='login')
def company_documents_data(request):
    """Return JSON list of documents for current filters/pagination for frontend updates."""
    # Build queryset using similar filters as company_documents_list
    status_filter = request.GET.get('status', 'all')
    type_filter = request.GET.get('type', 'all')
    scope_filter = request.GET.get('scope', 'all')
    search_query = request.GET.get('search', '').strip()

    documents_qs = CompanyDocument.objects.all().order_by('expiry_date')

    if scope_filter == 'vehicle':
        documents_qs = documents_qs.filter(
            Q(related_vehicle__isnull=False) | Q(related_asset__asset_type='vehicle')
        )
    elif scope_filter == 'equipment':
        documents_qs = documents_qs.filter(
            Q(related_equipment__isnull=False) | Q(related_asset__asset_type='equipment')
        )
    elif scope_filter == 'company':
        documents_qs = documents_qs.filter(
            Q(related_vehicle__isnull=True), Q(related_equipment__isnull=True)
        )

    if search_query:
        documents_qs = documents_qs.filter(
            Q(name__icontains=search_query) |
            Q(document_number__icontains=search_query) |
            Q(related_vehicle__name__icontains=search_query) |
            Q(related_asset__name__icontains=search_query)
        )

    if type_filter != 'all':
        documents_qs = documents_qs.filter(document_type=type_filter)

    # Apply status filter server-side only for pagination preview; keep logic simple
    if status_filter in ('expired', 'expiring', 'safe'):
        documents = [d for d in documents_qs if d.get_status() == status_filter]
    else:
        documents = list(documents_qs)

    # Paginate
    page = int(request.GET.get('page', 1))
    paginator = Paginator(documents, 20)
    try:
        page_obj = paginator.page(page)
    except Exception:
        page_obj = paginator.page(1)

    serialized = []
    for doc in page_obj.object_list:
        asset_info = None
        if doc.related_vehicle:
            asset_info = {
                'type': 'vehicle',
                'id': doc.related_vehicle.pk,
                'name': doc.related_vehicle.name,
                'license_plate': doc.related_vehicle.license_plate,
                'url': django_reverse('asset_detail', args=[doc.related_vehicle.pk]) + '?asset_type=vehicles'
            }
        elif doc.related_equipment:
            asset_info = {
                'type': 'equipment',
                'id': doc.related_equipment.pk,
                'name': doc.related_equipment.name,
                'url': django_reverse('equipment_detail', args=[doc.related_equipment.pk])
            }
        elif doc.related_asset:
            asset_info = {
                'type': doc.related_asset.asset_type,
                'id': doc.related_asset.pk,
                'name': str(doc.related_asset),
            }

        serialized.append({
            'id': doc.pk,
            'name': doc.name,
            'document_number': doc.document_number or '',
            'issuing_authority': doc.issuing_authority or '',
            'location': doc.location or '',
            'asset': asset_info,
            'expiry_date': doc.expiry_date.isoformat() if doc.expiry_date else None,
            'status': doc.get_status(),
            'days_until_expiry': doc.days_until_expiry() if hasattr(doc, 'days_until_expiry') else None,
            'responsible': doc.responsible_display,
        })

    return JsonResponse({
        'documents': serialized,
        'page': page_obj.number,
        'num_pages': paginator.num_pages,
        'total': paginator.count,
    })


@login_required(login_url='login')
@require_manager
def company_document_detail(request, pk):
    """View detail of a single company document"""
    document = get_object_or_404(CompanyDocument, pk=pk)
    context = {
        'document': document,
        'back_url': get_back_url(request, django_reverse('company_documents_list'))
    }
    
    log_audit(request.user, 'view', 'companydocument', object_id=pk, description=f'Viewed document: {document.name}')
    return render(request, 'company_documents/detail.html', context)


@require_admin
def staff_list(request):
    """Manager-facing list of staff members with search and pagination."""
    query = request.GET.get('q', '').strip()
    staff_qs = StaffMember.objects.all().order_by('staff_id')
    if query:
        staff_qs = staff_qs.filter(
            Q(staff_id__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(branch__icontains=query)
        )

    paginator = Paginator(staff_qs, 25)
    page = request.GET.get('page')
    try:
        staff_page = paginator.page(page)
    except PageNotAnInteger:
        staff_page = paginator.page(1)
    except EmptyPage:
        staff_page = paginator.page(paginator.num_pages)

    context = {
        'staff_members': staff_page,
        'query': query,
        'legacy_names': [
            name for name in get_legacy_assigned_names()
            if _normalize_staff_name(name) not in {
                _normalize_staff_name(f"{staff.first_name} {staff.last_name}")
                for staff in StaffMember.objects.all()
            }
        ]
    }
    return render(request, 'staff/list.html', context)


@require_admin
def staff_create(request):
    if request.method == 'POST':
        form = StaffMemberForm(request.POST)
        back_url = request.POST.get('back_url') or get_back_url(request, django_reverse('staff_list'))
        if form.is_valid():
            staff = form.save()
            log_audit(request.user, 'create', 'staffmember', object_id=staff.pk, description=f'Created staff {staff.staff_id}')
            messages.success(request, 'Staff member created')
            return redirect('staff_list')
    else:
        form = StaffMemberForm()
        back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('staff_list'))
    return render(request, 'staff/form.html', {'form': form, 'action': 'Add', 'back_url': back_url})


@require_admin
def staff_edit(request, pk):
    staff = get_object_or_404(StaffMember, pk=pk)
    if request.method == 'POST':
        form = StaffMemberForm(request.POST, instance=staff)
        back_url = request.POST.get('back_url') or get_back_url(request, django_reverse('staff_list'))
        if form.is_valid():
            form.save()
            log_audit(request.user, 'update', 'staffmember', object_id=staff.pk, description=f'Updated staff {staff.staff_id}')
            messages.success(request, 'Staff member updated')
            return redirect('staff_list')
    else:
        form = StaffMemberForm(instance=staff)
        back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('staff_list'))
    return render(request, 'staff/form.html', {'form': form, 'action': 'Edit', 'back_url': back_url})


@require_admin
def staff_delete(request, pk):
    staff = get_object_or_404(StaffMember, pk=pk)
    if request.method == 'POST':
        staff_id = staff.staff_id
        staff.delete()
        log_audit(request.user, 'delete', 'staffmember', description=f'Deleted staff {staff_id}')
        messages.success(request, 'Staff member deleted')
        return redirect('staff_list')
    return render(request, 'staff/confirm_delete.html', {'staff': staff})


@require_admin
def staff_import_legacy(request):
    if request.method != 'POST':
        return redirect('staff_list')
    auto_assign = bool(request.POST.get('auto_assign'))
    legacy_names = get_legacy_assigned_names()
    existing_names = {
        _normalize_staff_name(f"{staff.first_name} {staff.last_name}")
        for staff in StaffMember.objects.all()
    }
    imported = 0
    assigned_count = 0
    created_map = {}
    first_created_pk = None

    with transaction.atomic():
        for name in legacy_names:
            normalized = _normalize_staff_name(name)
            if normalized in existing_names:
                continue
            first_name, last_name = _split_name(name)
            staff = StaffMember.objects.create(
                user=None,
                staff_id=_generate_legacy_staff_id(name),
                first_name=first_name,
                last_name=last_name,
                is_active=True
            )
            if not first_created_pk:
                first_created_pk = staff.pk
            imported += 1
            existing_names.add(normalized)
            created_map[name] = staff
            log_audit(request.user, 'create', 'staffmember', object_id=staff.pk, description=f'Imported legacy staff {staff.staff_id}')

        if auto_assign and created_map:
            for name, staff in created_map.items():
                # Assign to equipment
                eq_qs = OfficeEquipment.objects.filter(assigned_user__iexact=name)
                for eq in eq_qs:
                    eq.assigned_staff = staff
                    eq.save()
                    assigned_count += 1
                    log_audit(request.user, 'update', 'officeequipment', object_id=eq.pk, description=f'Auto-assigned equipment {eq.pk} to staff {staff.staff_id}')

                # Assign to documents
                doc_qs = CompanyDocument.objects.filter(responsible_person__iexact=name)
                for doc in doc_qs:
                    doc.responsible_staff = staff
                    doc.save()
                    assigned_count += 1
                    log_audit(request.user, 'update', 'companydocument', object_id=doc.pk, description=f'Auto-assigned document {doc.pk} to staff {staff.staff_id}')

    if imported:
        if auto_assign:
            messages.success(request, f'Imported {imported} legacy staff names and auto-assigned {assigned_count} assets.')
        else:
            messages.success(request, f'Imported {imported} legacy staff names.')
        # Redirect to the first imported staff's edit page for manual staff_id editing
        if first_created_pk:
            return redirect('staff_edit', pk=first_created_pk)
    else:
        messages.info(request, 'No new legacy staff names were found to import.')
    return redirect('staff_list')


@login_required
def staff_autocomplete(request):
    """Simple JSON endpoint returning active staff matching a query string."""
    q = request.GET.get('q', '').strip()
    qs = StaffMember.objects.filter(is_active=True)
    if q:
        qs = qs.filter(
            Q(staff_id__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(email__icontains=q) |
            Q(branch__icontains=q)
        )
    results = []
    for s in qs[:20]:
        branch_label = f" ({s.branch})" if s.branch else ''
        results.append({
            'id': s.pk,
            'label': f"{s.staff_id} — {s.full_name}{branch_label}"
        })
    return JsonResponse(results, safe=False)


@login_required(login_url='login')
@require_admin
def company_document_create(request):
    """Create a new company document"""
    related_vehicle_id = request.GET.get('related_vehicle')
    related_equipment_id = request.GET.get('related_equipment')
    document_scope = request.GET.get('document_scope', 'company')
    initial = {}

    if related_equipment_id:
        initial['related_equipment'] = related_equipment_id
        document_scope = 'equipment'
    elif related_vehicle_id:
        initial['related_vehicle'] = related_vehicle_id
        document_scope = 'vehicle'
    elif document_scope not in ('company', 'vehicle', 'equipment'):
        document_scope = 'company'

    if request.method == 'POST':
        document_scope = request.POST.get('document_scope', 'company')
        form = CompanyDocumentForm(request.POST)
        back_url = request.POST.get('back_url') or get_back_url(request, django_reverse('company_documents_list'))
        if form.is_valid():
            document = form.save(commit=False)
            document.created_by = request.user
            document.save()
            
            log_audit(request.user, 'create', 'companydocument', object_id=document.pk, 
                     description=f'Created document: {document.name}')
            
            messages.success(request, f'Document "{document.name}" created successfully!')
            return redirect('company_document_detail', pk=document.pk)
    else:
        form = CompanyDocumentForm(initial=initial)
        back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('company_documents_list'))
    
    context = {'form': form, 'action': 'Create', 'document_scope': document_scope, 'back_url': back_url}
    return render(request, 'company_documents/form.html', context)


@login_required(login_url='login')
@require_manager
def company_document_edit(request, pk):
    """Edit an existing company document"""
    document = get_object_or_404(CompanyDocument, pk=pk)
    
    if document.related_equipment:
        document_scope = 'equipment'
    elif document.related_vehicle:
        document_scope = 'vehicle'
    else:
        document_scope = 'company'

    if request.method == 'POST':
        document_scope = request.POST.get('document_scope', document_scope)
        form = CompanyDocumentForm(request.POST, instance=document)
        back_url = request.POST.get('back_url') or get_back_url(request, django_reverse('company_document_detail', args=[pk]))
        if form.is_valid():
            form.save()
            
            log_audit(request.user, 'edit', 'companydocument', object_id=pk, 
                     description=f'Updated document: {document.name}')
            
            messages.success(request, f'Document "{document.name}" updated successfully!')
            return redirect('company_document_detail', pk=pk)
    else:
        form = CompanyDocumentForm(instance=document)
        back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('company_document_detail', args=[pk]))
    
    context = {'form': form, 'document': document, 'action': 'Edit', 'document_scope': document_scope, 'back_url': back_url}
    return render(request, 'company_documents/form.html', context)


@login_required(login_url='login')
@require_manager
def company_document_delete(request, pk):
    """Delete a company document"""
    document = get_object_or_404(CompanyDocument, pk=pk)
    
    back_url = request.GET.get('back_url') or get_back_url(request, django_reverse('company_documents_list'))

    if request.method == 'POST':
        doc_name = document.name
        document.delete()
        
        log_audit(request.user, 'delete', 'companydocument', object_id=pk, 
                 description=f'Deleted document: {doc_name}')
        
        messages.success(request, f'Document "{doc_name}" deleted successfully!')
        return redirect('company_documents_list')
    
    context = {'document': document, 'back_url': back_url}
    return render(request, 'company_documents/delete_confirm.html', context)
