from django.db import transaction
from django.utils import timezone

from .models import Asset, AssetAssignmentRequest, EquipmentTransfer
from .permissions import is_admin
from .approval_workflow import (
    approval_records_complete,
    create_approval_records,
    pending_approval_for_actor,
    set_approval_record_status,
    sync_assignment_approval_fields,
    sync_assignment_approval_records,
    validate_approval_actor,
)


class AssignmentWorkflowError(Exception):
    pass


@transaction.atomic
def submit_assignment_request(asset, staff_member, requested_by, reason='', notes=''):
    asset = Asset.objects.select_for_update().get(pk=asset.pk)
    if not staff_member.is_active:
        raise AssignmentWorkflowError('Only active staff can receive an asset.')
    if asset.assigned_staff_id == staff_member.pk:
        return None
    if asset.assignment_requests.filter(status='pending').exists():
        raise AssignmentWorkflowError('This asset already has a pending assignment request.')

    supervisor = staff_member.supervisor
    manager = staff_member.reporting_manager
    supervisor_user = supervisor.user_id if supervisor and supervisor.user_id and supervisor.user.is_active else None
    manager_user = manager.user_id if manager and manager.user_id and manager.user.is_active else None
    assignment = AssetAssignmentRequest.objects.create(
        asset=asset,
        previous_staff=asset.assigned_staff,
        requested_staff=staff_member,
        requested_by=requested_by,
        reason=reason,
        notes=notes,
        supervisor_approver_id=supervisor_user,
        reporting_manager_approver_id=manager_user,
        supervisor_approval_required=supervisor is not None,
        reporting_manager_approval_required=manager is not None,
        requires_superadmin_approval=not (supervisor_user and manager_user),
    )
    create_approval_records(
        assignment,
        [('supervisor', supervisor_user), ('reporting_manager', manager_user)],
        admin_fallback=assignment.requires_superadmin_approval,
    )
    return assignment


@transaction.atomic
def approve_assignment_request(assignment_request_id, user, approval_record=None):
    assignment = AssetAssignmentRequest.objects.select_for_update().get(pk=assignment_request_id)
    if assignment.status != 'pending':
        raise AssignmentWorkflowError('This assignment request is no longer pending.')

    if assignment.approval_records.exists():
        approval_record = approval_record or pending_approval_for_actor(assignment, user)
        if not approval_record or approval_record.asset_assignment_request_id != assignment.pk:
            raise PermissionError('You are not an approver for this assignment request.')
        validate_approval_actor(approval_record, user)
        set_approval_record_status(approval_record, user, 'approved')
        sync_assignment_approval_fields(assignment, approval_record)
        if approval_records_complete(assignment):
            if not assignment.approvals_complete:
                raise AssignmentWorkflowError('The required assignment approvals are incomplete.')
            return apply_approved_assignment(assignment)
        return assignment

    now = timezone.now()
    approved_fields = []
    if assignment.supervisor_approver_id == user.pk and not assignment.supervisor_approved_at:
        assignment.supervisor_approved_by = user
        assignment.supervisor_approved_at = now
        approved_fields.extend(['supervisor_approved_by', 'supervisor_approved_at'])
    if assignment.reporting_manager_approver_id == user.pk and not assignment.reporting_manager_approved_at:
        assignment.reporting_manager_approved_by = user
        assignment.reporting_manager_approved_at = now
        approved_fields.extend(['reporting_manager_approved_by', 'reporting_manager_approved_at'])
    if is_admin(user):
        supervisor_unavailable = (
            assignment.supervisor_approver_id is None or
            not assignment.supervisor_approver.is_active
        ) if assignment.supervisor_approver_id else True
        manager_unavailable = (
            assignment.reporting_manager_approver_id is None or
            not assignment.reporting_manager_approver.is_active
        ) if assignment.reporting_manager_approver_id else True
        if assignment.supervisor_approval_required and supervisor_unavailable and not assignment.supervisor_approved_at:
            assignment.supervisor_approved_by = user
            assignment.supervisor_approved_at = now
            approved_fields.extend(['supervisor_approved_by', 'supervisor_approved_at'])
        if assignment.reporting_manager_approval_required and manager_unavailable and not assignment.reporting_manager_approved_at:
            assignment.reporting_manager_approved_by = user
            assignment.reporting_manager_approved_at = now
            approved_fields.extend(['reporting_manager_approved_by', 'reporting_manager_approved_at'])
        if assignment.requires_superadmin_approval and not assignment.superadmin_approved_at:
            assignment.superadmin_approved_by = user
            assignment.superadmin_approved_at = now
            approved_fields.extend(['superadmin_approved_by', 'superadmin_approved_at'])

    if not approved_fields:
        raise PermissionError('You are not an approver for this assignment request.')

    assignment.save(update_fields=approved_fields + ['updated_at'])
    sync_assignment_approval_records(assignment)
    if assignment.approvals_complete:
        return apply_approved_assignment(assignment)

    return assignment


def apply_approved_assignment(assignment):
    asset = Asset.objects.select_for_update().get(pk=assignment.asset_id)
    if asset.assigned_staff_id != assignment.previous_staff_id:
        assignment.status = 'rejected'
        assignment.rejection_note = 'The asset assignment changed while this request was awaiting approval.'
        assignment.save(update_fields=['status', 'rejection_note', 'updated_at'])
        return assignment

    asset.assigned_staff = assignment.requested_staff
    asset.save(update_fields=['assigned_staff'])
    company_asset = getattr(asset, 'company_asset', None)
    equipment = getattr(asset, 'equipment', None)
    if company_asset:
        company_asset.assigned_staff = assignment.requested_staff
        company_asset.save(update_fields=['assigned_staff'])
    if equipment:
        previous_user_label = equipment.assigned_user or (
            str(assignment.previous_staff) if assignment.previous_staff else 'Unassigned'
        )
        equipment.assigned_staff = assignment.requested_staff
        equipment.save(update_fields=['assigned_staff'])
        equipment.assigned_user = assignment.requested_staff.full_name
        equipment.save(update_fields=['assigned_user'])
        EquipmentTransfer.objects.create(
            equipment=equipment,
            transferred_from=previous_user_label,
            transferred_from_department=assignment.previous_staff.department or '' if assignment.previous_staff else '',
            transferred_from_email=assignment.previous_staff.email or '' if assignment.previous_staff else '',
            transferred_to=str(assignment.requested_staff),
            transferred_to_department=assignment.requested_staff.department or '',
            transferred_to_email=assignment.requested_staff.email or '',
            reason=assignment.reason,
            notes=assignment.notes,
            recorded_by=assignment.requested_by,
        )
    assignment.status = 'approved'
    assignment.save(update_fields=['status', 'updated_at'])
    return assignment


@transaction.atomic
def reject_assignment_request(assignment_request_id, user, rejection_note='', approval_record=None):
    assignment = AssetAssignmentRequest.objects.select_for_update().get(pk=assignment_request_id)
    if assignment.status != 'pending':
        raise AssignmentWorkflowError('This assignment request is no longer pending.')
    if assignment.approval_records.exists():
        approval_record = approval_record or pending_approval_for_actor(assignment, user)
        if not approval_record or approval_record.asset_assignment_request_id != assignment.pk:
            raise PermissionError('You are not an approver for this assignment request.')
        validate_approval_actor(approval_record, user)
        set_approval_record_status(approval_record, user, 'rejected', rejection_note)
    else:
        authorized = is_admin(user) or user.pk in {
            assignment.supervisor_approver_id,
            assignment.reporting_manager_approver_id,
        }
        if not authorized:
            raise PermissionError('You are not an approver for this assignment request.')
    assignment.status = 'rejected'
    assignment.rejected_by = user
    assignment.rejection_note = rejection_note
    assignment.save(update_fields=['status', 'rejected_by', 'rejection_note', 'updated_at'])
    return assignment


@transaction.atomic
def save_record_with_assignment_request(form, user):
    record = form.save(commit=False)
    requested_staff = record.assigned_staff
    previous_staff = None
    if record.pk:
        previous_staff = type(record).objects.get(pk=record.pk).assigned_staff

    assignment_changed = requested_staff and requested_staff.pk != getattr(previous_staff, 'pk', None)
    if assignment_changed:
        record.assigned_staff = previous_staff
    record.save()
    form.save_m2m()

    if assignment_changed:
        submit_assignment_request(record.asset, requested_staff, user)
    return record, bool(assignment_changed)