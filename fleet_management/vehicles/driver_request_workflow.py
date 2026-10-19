from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .approval_workflow import (
    approval_records_complete,
    create_approval_records,
    pending_approval_for_actor,
    set_approval_record_status,
    validate_approval_actor,
)
from .models import CompanyAsset, DriverRequest, StaffMember
from .permissions import is_admin


class DriverRequestWorkflowError(Exception):
    pass


def get_available_drivers(
    requested_start,
    requested_end,
    exclude_request_id=None,
    include_driver_id=None,
):
    if not requested_start or not requested_end:
        return StaffMember.objects.none()
    overlapping = Q(assigned_driver_requests__status='assigned') & (
        Q(assigned_driver_requests__requested_start__isnull=True)
        | Q(assigned_driver_requests__requested_end__isnull=True)
        | Q(
            assigned_driver_requests__requested_start__lt=requested_end,
            assigned_driver_requests__requested_end__gt=requested_start,
        )
    )
    if exclude_request_id:
        overlapping &= ~Q(assigned_driver_requests__pk=exclude_request_id)
    availability = Q(driver_status='available')
    if include_driver_id:
        availability |= Q(pk=include_driver_id)
    return StaffMember.objects.filter(
        user__role__role='driver',
        is_active=True,
    ).filter(availability).exclude(overlapping).distinct().order_by('staff_id')


def prepare_driver_request_approval(driver_request):
    staff = driver_request.requested_by
    approvers = []
    if staff:
        for approver_type, staff_approver in (
            ('supervisor', staff.supervisor),
            ('reporting_manager', staff.reporting_manager),
        ):
            if staff_approver and staff_approver.user_id and staff_approver.user.is_active:
                approvers.append((approver_type, staff_approver.user))

    approver = approvers[0][1] if approvers else None
    driver_request.approval_approver = approver
    driver_request.requires_superadmin_approval = not approvers
    driver_request.save(update_fields=[
        'approval_approver', 'requires_superadmin_approval', 'updated_at',
    ])
    create_approval_records(
        driver_request,
        approvers,
        admin_fallback=not approvers,
    )
    return driver_request


def can_approve_driver_request(driver_request, user):
    if driver_request.status != 'requested' or not user.is_authenticated:
        return False
    if driver_request.approval_records.exists():
        return pending_approval_for_actor(driver_request, user) is not None
    if driver_request.approval_approver_id == user.pk:
        return True
    return is_admin(user) and (
        driver_request.requires_superadmin_approval
        or driver_request.approval_approver_id is None
        or not driver_request.approval_approver.is_active
    )


@transaction.atomic
def approve_driver_request(driver_request_id, user, approval_record=None):
    driver_request = DriverRequest.objects.select_for_update().get(pk=driver_request_id)
    if driver_request.approval_records.exists():
        approval_record = approval_record or pending_approval_for_actor(driver_request, user)
        if not approval_record or approval_record.driver_request_id != driver_request.pk:
            raise PermissionError('You are not an approver for this driver request.')
        validate_approval_actor(approval_record, user)
        set_approval_record_status(approval_record, user, 'approved')
        if approval_records_complete(driver_request):
            driver_request.approved_by = user
            driver_request.approved_at = timezone.now()
            driver_request.status = 'approved'
            driver_request.save(update_fields=[
                'approved_by', 'approved_at', 'status', 'updated_at',
            ])
        return driver_request

    if not can_approve_driver_request(driver_request, user):
        raise PermissionError('You are not an approver for this driver request.')

    driver_request.approved_by = user
    driver_request.approved_at = timezone.now()
    driver_request.status = 'approved'
    driver_request.save(update_fields=[
        'approved_by', 'approved_at', 'status', 'updated_at',
    ])
    return driver_request


@transaction.atomic
def reject_driver_request(driver_request_id, user, rejection_note='', approval_record=None):
    driver_request = DriverRequest.objects.select_for_update().get(pk=driver_request_id)
    if driver_request.approval_records.exists():
        approval_record = approval_record or pending_approval_for_actor(driver_request, user)
        if not approval_record or approval_record.driver_request_id != driver_request.pk:
            raise PermissionError('You are not an approver for this driver request.')
        validate_approval_actor(approval_record, user)
        set_approval_record_status(approval_record, user, 'rejected', rejection_note)
        driver_request.status = 'declined'
        driver_request.rejected_by = user
        driver_request.rejected_at = timezone.now()
        driver_request.rejection_note = rejection_note
        driver_request.save(update_fields=[
            'status', 'rejected_by', 'rejected_at', 'rejection_note', 'updated_at',
        ])
        return driver_request

    if not can_approve_driver_request(driver_request, user):
        raise PermissionError('You are not an approver for this driver request.')

    driver_request.status = 'declined'
    driver_request.rejected_by = user
    driver_request.rejected_at = timezone.now()
    driver_request.rejection_note = rejection_note
    driver_request.save(update_fields=[
        'status', 'rejected_by', 'rejected_at', 'rejection_note', 'updated_at',
    ])
    return driver_request


def get_available_vehicles(
    requested_start,
    requested_end,
    exclude_request_id=None,
    assigned_driver_id=None,
):
    reserved_during_window = Q(driver_requests__status='assigned') & (
        Q(driver_requests__requested_start__isnull=True)
        | Q(driver_requests__requested_end__isnull=True)
        | Q(
            driver_requests__requested_start__lt=requested_end,
            driver_requests__requested_end__gt=requested_start,
        )
    )
    if exclude_request_id:
        reserved_during_window &= ~Q(driver_requests__pk=exclude_request_id)
    vehicles = CompanyAsset.objects.filter(status='active')
    if assigned_driver_id:
        vehicles = vehicles.filter(
            Q(assigned_staff__isnull=True) | Q(assigned_staff_id=assigned_driver_id)
        )
    else:
        vehicles = vehicles.filter(
            Q(assigned_staff__isnull=True)
            | Q(assigned_staff__user__role__role='driver', assigned_staff__is_active=True)
        )
    vehicles = vehicles.exclude(reserved_during_window)
    return vehicles.distinct().order_by('name')


def _vehicle_is_available(vehicle, driver_request, assigned_driver):
    if vehicle.status != 'active':
        return False
    if vehicle.assigned_staff_id not in (None, assigned_driver.pk):
        return False
    if not driver_request.requested_start or not driver_request.requested_end:
        return False
    conflicts = DriverRequest.objects.filter(
        assigned_vehicle=vehicle,
        status='assigned',
    ).exclude(pk=driver_request.pk).filter(
        Q(requested_start__isnull=True)
        | Q(requested_end__isnull=True)
        | Q(
            requested_start__lt=driver_request.requested_end,
            requested_end__gt=driver_request.requested_start,
        )
    )
    return not conflicts.exists()


def _driver_is_available(driver, driver_request):
    if not driver.is_active or not driver.user_id:
        return False
    if getattr(getattr(driver.user, 'role', None), 'role', None) != 'driver':
        return False
    if driver.pk == driver_request.assigned_driver_id:
        return True
    return get_available_drivers(
        driver_request.requested_start,
        driver_request.requested_end,
        exclude_request_id=driver_request.pk,
        include_driver_id=driver_request.assigned_driver_id,
    ).filter(pk=driver.pk).exists()


@transaction.atomic
def assign_driver_request(driver_request_id, user, assigned_driver_id, assigned_vehicle_id, notes=None):
    driver_request = DriverRequest.objects.select_for_update().get(pk=driver_request_id)
    if driver_request.status not in ('approved', 'assigned'):
        raise DriverRequestWorkflowError('The request must be approved before dispatch.')

    assigned_driver = StaffMember.objects.select_for_update().filter(
        pk=assigned_driver_id,
    ).first()
    if not assigned_driver or not _driver_is_available(assigned_driver, driver_request):
        raise DriverRequestWorkflowError('Select an active driver who is available.')

    assigned_vehicle = CompanyAsset.objects.select_for_update().filter(
        pk=assigned_vehicle_id,
    ).first()
    if not assigned_vehicle or not _vehicle_is_available(
        assigned_vehicle, driver_request, assigned_driver
    ):
        raise DriverRequestWorkflowError('Select an active vehicle that is available for the requested time.')

    driver_request.assigned_driver = assigned_driver
    driver_request.assigned_vehicle = assigned_vehicle
    driver_request.assigned_by = user
    driver_request.assigned_at = timezone.now()
    driver_request.status = 'assigned'
    if notes is not None:
        driver_request.notes = notes
    driver_request.save(update_fields=[
        'assigned_driver', 'assigned_vehicle', 'assigned_by', 'assigned_at',
        'status', 'notes', 'updated_at',
    ])
    return driver_request