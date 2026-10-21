from django.db.models import Q
from django.utils import timezone

from .models import ApprovalRecord, AssetAssignmentRequest, DriverRequest
from .permissions import is_admin


class ApprovalWorkflowError(Exception):
    pass


def create_approval_records(target, approvers, admin_fallback=False):
    if isinstance(target, AssetAssignmentRequest):
        target_field = 'asset_assignment_request'
    elif isinstance(target, DriverRequest):
        target_field = 'driver_request'
    else:
        raise TypeError('Unsupported approval target.')

    records = []
    for approver_type, user in approvers:
        if user:
            user_id = getattr(user, 'pk', user)
            records.append(ApprovalRecord.objects.create(
                **{target_field: target},
                approver_id=user_id,
                approver_type=approver_type,
            ))

    if admin_fallback:
        records.append(ApprovalRecord.objects.create(
            **{target_field: target},
            approver_type='admin',
        ))
    return records


def approval_records_for(target):
    if isinstance(target, AssetAssignmentRequest):
        return target.approval_records
    if isinstance(target, DriverRequest):
        return target.approval_records
    raise TypeError('Unsupported approval target.')


def approval_records_complete(target):
    records = approval_records_for(target)
    return records.exists() and not records.exclude(status='approved').exists()


def actor_approval_filter(user):
    query = Q(approver_id=user.pk)
    if is_admin(user):
        query |= Q(approver__isnull=True, approver_type='admin')
    return query


def pending_approval_for_actor(target, user):
    return approval_records_for(target).filter(
        actor_approval_filter(user),
        status='pending',
    ).order_by('created_at', 'pk').first()


def validate_approval_actor(approval, user):
    if approval.status != 'pending':
        raise ApprovalWorkflowError('This approval is no longer pending.')
    if approval.approver_id == user.pk:
        return
    if is_admin(user) and approval.approver_type == 'admin' and approval.approver_id is None:
        return
    raise PermissionError('You are not an approver for this approval.')


def set_approval_record_status(approval, actor, action, rejection_note=''):
    approval.status = action
    approval.acted_by = actor
    approval.acted_at = timezone.now()
    approval.rejection_note = rejection_note if action == 'rejected' else ''
    approval.save(update_fields=['status', 'acted_by', 'acted_at', 'rejection_note', 'updated_at'])

    if action == 'rejected':
        approval_records_for(approval_target(approval)).filter(status='pending').exclude(
            pk=approval.pk,
        ).update(
            status='cancelled',
            acted_by=actor,
            acted_at=approval.acted_at,
            updated_at=approval.acted_at,
        )
    return approval


def approval_target(approval):
    return approval.asset_assignment_request or approval.driver_request


def sync_assignment_approval_fields(assignment, approval):
    now = approval.acted_at or timezone.now()
    fields = []

    if approval.approver_type in ('supervisor', 'supervisor_and_reporting_manager'):
        if assignment.supervisor_approval_required:
            assignment.supervisor_approved_by = approval.acted_by
            assignment.supervisor_approved_at = now
            fields.extend(['supervisor_approved_by', 'supervisor_approved_at'])
    if approval.approver_type in ('reporting_manager', 'supervisor_and_reporting_manager'):
        if assignment.reporting_manager_approval_required:
            assignment.reporting_manager_approved_by = approval.acted_by
            assignment.reporting_manager_approved_at = now
            fields.extend(['reporting_manager_approved_by', 'reporting_manager_approved_at'])
    if approval.approver_type == 'admin':
        assignment.superadmin_approved_by = approval.acted_by
        assignment.superadmin_approved_at = now
        fields.extend(['superadmin_approved_by', 'superadmin_approved_at'])
        if assignment.supervisor_approval_required and not assignment.supervisor_approver_id:
            assignment.supervisor_approved_by = approval.acted_by
            assignment.supervisor_approved_at = now
            fields.extend(['supervisor_approved_by', 'supervisor_approved_at'])
        if assignment.reporting_manager_approval_required and not assignment.reporting_manager_approver_id:
            assignment.reporting_manager_approved_by = approval.acted_by
            assignment.reporting_manager_approved_at = now
            fields.extend(['reporting_manager_approved_by', 'reporting_manager_approved_at'])

    if fields:
        assignment.save(update_fields=list(dict.fromkeys(fields + ['updated_at'])))


def sync_assignment_approval_records(assignment):
    for approval in assignment.approval_records.filter(status='pending').select_related('approver'):
        fields = []
        if approval.approver_type in ('supervisor', 'supervisor_and_reporting_manager'):
            if assignment.supervisor_approved_at:
                fields.extend(['supervisor_approved_by', 'supervisor_approved_at'])
        if approval.approver_type in ('reporting_manager', 'supervisor_and_reporting_manager'):
            if assignment.reporting_manager_approved_at:
                fields.extend(['reporting_manager_approved_by', 'reporting_manager_approved_at'])
        if approval.approver_type == 'admin' and assignment.superadmin_approved_at:
            fields.extend(['superadmin_approved_by', 'superadmin_approved_at'])
        if fields and all(getattr(assignment, field) for field in fields if field.endswith('_at')):
            approval.status = 'approved'
            approval.acted_by = assignment.superadmin_approved_by or (
                assignment.supervisor_approved_by
                if approval.approver_type == 'supervisor'
                else assignment.reporting_manager_approved_by
            )
            approval.acted_at = assignment.superadmin_approved_at or (
                assignment.supervisor_approved_at
                if approval.approver_type == 'supervisor'
                else assignment.reporting_manager_approved_at
            )
            approval.save(update_fields=['status', 'acted_by', 'acted_at', 'updated_at'])
