from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .asset_assignment_workflow import approve_assignment_request, reject_assignment_request, submit_assignment_request
from .forms import StaffMemberForm
from .models import (
    ApprovalRecord,
    Asset,
    AssetAssignmentRequest,
    DriverRequest,
    EquipmentTransfer,
    OfficeEquipment,
    StaffMember,
    UserRole,
)


class AssetAssignmentApprovalTests(TestCase):
    def setUp(self):
        self.superadmin = User.objects.create_superuser(
            username='assignment-superadmin', email='superadmin@example.test', password='pass'
        )
        self.admin_user = User.objects.create_user('assignment-admin', password='pass')
        UserRole.objects.create(user=self.admin_user, role='admin')
        self.manager_user = User.objects.create_user('assignment-manager', password='pass')
        self.supervisor_user = User.objects.create_user('assignment-supervisor', password='pass')
        self.requester = User.objects.create_user('assignment-requester', password='pass')
        UserRole.objects.create(user=self.manager_user, role='staff')
        UserRole.objects.create(user=self.supervisor_user, role='staff')
        self.manager = StaffMember.objects.create(
            user=self.manager_user, staff_id='MGR-001', first_name='Morgan', last_name='Manager'
        )
        self.supervisor = StaffMember.objects.create(
            user=self.supervisor_user, staff_id='SUP-001', first_name='Sam', last_name='Supervisor'
        )
        self.assignee = StaffMember.objects.create(
            staff_id='EMP-001', first_name='Ari', last_name='Employee',
            reporting_manager=self.manager, supervisor=self.supervisor,
        )
        self.asset = Asset.objects.create(name='Approval Test Asset')

    def test_assignment_waits_for_both_manager_and_supervisor(self):
        request = submit_assignment_request(self.asset, self.assignee, self.requester)

        self.asset.refresh_from_db()
        self.assertIsNone(self.asset.assigned_staff)
        self.assertEqual(request.status, 'pending')
        self.assertFalse(request.requires_superadmin_approval)

        approve_assignment_request(request.pk, self.manager_user)
        self.asset.refresh_from_db()
        request.refresh_from_db()
        self.assertIsNone(self.asset.assigned_staff)
        self.assertEqual(request.status, 'pending')

        approve_assignment_request(request.pk, self.supervisor_user)
        self.asset.refresh_from_db()
        request.refresh_from_db()
        self.assertEqual(self.asset.assigned_staff, self.assignee)
        self.assertEqual(request.status, 'approved')
        self.assertEqual(self.asset.assignments.filter(released_at__isnull=True).count(), 1)

    def test_missing_supervisor_requires_superadmin_in_addition_to_manager(self):
        self.assignee.supervisor = None
        self.assignee.save(update_fields=['supervisor'])
        request = submit_assignment_request(self.asset, self.assignee, self.requester)
        self.assertTrue(request.requires_superadmin_approval)

        approve_assignment_request(request.pk, self.manager_user)
        self.asset.refresh_from_db()
        self.assertIsNone(self.asset.assigned_staff)

        approve_assignment_request(request.pk, self.admin_user)
        self.asset.refresh_from_db()
        request.refresh_from_db()
        self.assertEqual(self.asset.assigned_staff, self.assignee)
        self.assertEqual(request.status, 'approved')

    def test_no_manager_or_supervisor_can_be_approved_by_superadmin(self):
        self.assignee.reporting_manager = None
        self.assignee.supervisor = None
        self.assignee.save(update_fields=['reporting_manager', 'supervisor'])
        request = submit_assignment_request(self.asset, self.assignee, self.requester)

        approve_assignment_request(request.pk, self.superadmin)

        self.asset.refresh_from_db()
        request.refresh_from_db()
        self.assertEqual(self.asset.assigned_staff, self.assignee)
        self.assertEqual(request.status, 'approved')

    def test_rejection_leaves_assignment_unchanged(self):
        request = submit_assignment_request(self.asset, self.assignee, self.requester)

        reject_assignment_request(request.pk, self.manager_user, 'Not approved')

        self.asset.refresh_from_db()
        request.refresh_from_db()
        self.assertIsNone(self.asset.assigned_staff)
        self.assertEqual(request.status, 'rejected')
        self.assertEqual(request.rejection_note, 'Not approved')

    def test_approved_equipment_assignment_updates_linked_records_and_transfer_history(self):
        previous_staff = StaffMember.objects.create(
            staff_id='EMP-OLD', first_name='Old', last_name='Assignee'
        )
        self.asset.assigned_staff = previous_staff
        self.asset.save(update_fields=['assigned_staff'])
        equipment = OfficeEquipment.objects.create(
            name='Approval Test Equipment', asset=self.asset, assigned_staff=previous_staff,
            assigned_user=previous_staff.full_name,
        )
        request = submit_assignment_request(
            self.asset, self.assignee, self.requester, reason='Reassignment', notes='Move to new team'
        )

        approve_assignment_request(request.pk, self.manager_user)
        approve_assignment_request(request.pk, self.supervisor_user)

        self.asset.refresh_from_db()
        equipment.refresh_from_db()
        self.assertEqual(self.asset.assigned_staff, self.assignee)
        self.assertEqual(equipment.assigned_staff, self.assignee)
        self.assertEqual(equipment.assigned_user, self.assignee.full_name)
        transfer = EquipmentTransfer.objects.get(equipment=equipment)
        self.assertEqual(transfer.reason, 'Reassignment')
        self.assertEqual(transfer.notes, 'Move to new team')

    def test_equipment_transfer_screen_submits_request_without_changing_assignment(self):
        equipment = OfficeEquipment.objects.create(name='Transfer Screen Equipment')
        client = self.client
        client.force_login(self.superadmin)

        response = client.post(reverse('equipment_transfer', args=[equipment.pk]), {
            'transferred_to': self.assignee.pk,
            'reason': 'Team change',
        })

        self.assertEqual(response.status_code, 302)
        equipment.refresh_from_db()
        self.assertIsNone(equipment.assigned_staff)
        self.assertEqual(equipment.asset.assignment_requests.filter(status='pending').count(), 1)

    def test_staff_form_has_optional_searchable_manager_and_supervisor(self):
        form = StaffMemberForm()

        self.assertFalse(form.fields['reporting_manager'].required)
        self.assertFalse(form.fields['supervisor'].required)
        self.assertEqual(form.fields['reporting_manager'].widget.attrs['data-autocomplete'], 'staff')
        self.assertEqual(form.fields['supervisor'].widget.attrs['data-autocomplete'], 'staff')
        self.assertIn(self.manager, form.fields['supervisor'].queryset)
        self.assertIn(self.supervisor, form.fields['supervisor'].queryset)

    def test_assignment_api_creates_request_without_assigning_asset(self):
        client = APIClient()
        client.force_authenticate(self.superadmin)

        response = client.post(
            reverse('asset-assign', args=[self.asset.pk]),
            {'staff_id': self.assignee.pk},
            format='json',
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(AssetAssignmentRequest.objects.get().requested_staff, self.assignee)
        self.asset.refresh_from_db()
        self.assertIsNone(self.asset.assigned_staff)

    def test_assignment_approval_api_waits_for_both_approvers(self):
        assignment = submit_assignment_request(self.asset, self.assignee, self.requester)
        client = APIClient()

        client.force_authenticate(self.manager_user)
        manager_response = client.post(
            reverse('asset-assignment-request-approve', args=[assignment.pk]),
            format='json',
        )
        self.assertEqual(manager_response.status_code, 200)
        self.assertEqual(manager_response.data['status'], 'pending')
        self.assertFalse(manager_response.data['approvals_complete'])

        client.force_authenticate(self.supervisor_user)
        supervisor_response = client.post(
            reverse('asset-assignment-request-approve', args=[assignment.pk]),
            format='json',
        )
        self.assertEqual(supervisor_response.status_code, 200)
        self.assertEqual(supervisor_response.data['status'], 'approved')
        self.assertTrue(supervisor_response.data['approvals_complete'])
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.assigned_staff, self.assignee)

    def test_assignment_approval_api_uses_admin_when_approvers_are_missing(self):
        self.assignee.reporting_manager = None
        self.assignee.supervisor = None
        self.assignee.save(update_fields=['reporting_manager', 'supervisor'])
        assignment = submit_assignment_request(self.asset, self.assignee, self.requester)
        client = APIClient()
        client.force_authenticate(self.admin_user)

        response = client.post(
            reverse('asset-assignment-request-approve', args=[assignment.pk]),
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'approved')
        self.assertTrue(response.data['requires_superadmin_approval'])
        self.assertEqual(response.data['superadmin_approved_by'], self.admin_user.pk)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.assigned_staff, self.assignee)

    def test_assignment_approval_api_rejects_unrelated_user(self):
        assignment = submit_assignment_request(self.asset, self.assignee, self.requester)
        client = APIClient()
        client.force_authenticate(self.requester)

        response = client.post(
            reverse('asset-assignment-request-approve', args=[assignment.pk]),
            format='json',
        )

        self.assertEqual(response.status_code, 403)
        self.asset.refresh_from_db()
        self.assertIsNone(self.asset.assigned_staff)

    def test_assignment_request_detail_api_exposes_approval_state_to_requester(self):
        assignment = submit_assignment_request(self.asset, self.assignee, self.requester)
        client = APIClient()
        client.force_authenticate(self.requester)

        response = client.get(reverse('asset-assignment-request-detail', args=[assignment.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'pending')
        self.assertTrue(response.data['supervisor_approval_required'])
        self.assertTrue(response.data['reporting_manager_approval_required'])

    def test_assignment_reject_api_records_rejection_without_reassigning(self):
        assignment = submit_assignment_request(self.asset, self.assignee, self.requester)
        client = APIClient()
        client.force_authenticate(self.manager_user)

        response = client.post(
            reverse('asset-assignment-request-reject', args=[assignment.pk]),
            {'rejection_note': 'Not approved'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'rejected')
        self.assertEqual(response.data['rejection_note'], 'Not approved')
        self.asset.refresh_from_db()
        self.assertIsNone(self.asset.assigned_staff)

    def test_generic_asset_update_api_queues_assignment(self):
        client = APIClient()
        client.force_authenticate(self.superadmin)

        response = client.put(
            reverse('asset-detail', args=[self.asset.pk]),
            {'name': self.asset.name, 'assigned_staff': self.assignee.pk},
            format='json',
        )

        self.assertEqual(response.status_code, 202)
        self.asset.refresh_from_db()
        self.assertIsNone(self.asset.assigned_staff)
        self.assertEqual(self.asset.assignment_requests.count(), 1)

    def test_vehicle_api_creation_returns_pending_assignment_request(self):
        client = APIClient()
        client.force_authenticate(self.superadmin)

        response = client.post('/api/vehicles/', {
            'name': 'API Approval Vehicle',
            'license_plate': 'API-APPROVAL-1',
            'assigned_staff': self.assignee.pk,
        }, format='json')

        self.assertEqual(response.status_code, 202)
        request = AssetAssignmentRequest.objects.get(pk=response.data['request_id'])
        self.assertEqual(request.requested_staff, self.assignee)
        vehicle = request.asset.company_asset
        self.assertIsNone(vehicle.assigned_staff)

    def test_approval_inbox_records_manager_approval_without_applying_assignment(self):
        assignment = submit_assignment_request(self.asset, self.assignee, self.requester)
        client = self.client
        client.force_login(self.manager_user)

        inbox = client.get(reverse('asset_assignment_approvals'))
        self.assertContains(inbox, self.asset.name)
        response = client.post(reverse('asset_assignment_approval_action', args=[assignment.pk]), {
            'action': 'approve',
        })

        self.assertEqual(response.status_code, 302)
        self.asset.refresh_from_db()
        assignment.refresh_from_db()
        self.assertIsNone(self.asset.assigned_staff)
        self.assertIsNotNone(assignment.reporting_manager_approved_at)
        self.assertEqual(assignment.status, 'pending')

    def test_admin_staff_api_stores_and_returns_manager_profile_ids(self):
        client = APIClient()
        client.force_authenticate(self.superadmin)

        update = client.patch(
            reverse('api-v1-admin-staff-detail', args=[self.assignee.pk]),
            {'supervisor': self.supervisor.pk, 'reporting_manager': self.manager.pk},
            format='json',
        )

        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.data['supervisor'], self.supervisor.pk)
        self.assertEqual(update.data['reporting_manager'], self.manager.pk)
        self.assignee.refresh_from_db()
        self.assertEqual(self.assignee.supervisor_id, self.supervisor.pk)
        self.assertEqual(self.assignee.reporting_manager_id, self.manager.pk)

        listing = client.get(reverse('api-v1-admin-staff'))
        result = next(item for item in listing.data['results'] if item['id'] == self.assignee.pk)
        self.assertEqual(result['supervisor'], self.supervisor.pk)
        self.assertEqual(result['reporting_manager'], self.manager.pk)

    def test_admin_v1_staff_create_returns_supervisor_and_reporting_manager_ids(self):
        client = APIClient()
        client.force_authenticate(self.superadmin)

        with patch('vehicles.api_v1.provision_staff_account', side_effect=lambda staff, request: staff.save()):
            response = client.post('/api/v1/admin/staff/', {
                'staff_id': 'API-V1-APPROVAL-STAFF',
                'first_name': 'V1',
                'last_name': 'Approval Staff',
                'email': 'api-v1-approval-staff@example.test',
                'supervisor': self.supervisor.pk,
                'reporting_manager': self.manager.pk,
            }, format='json')

        self.assertEqual(response.status_code, 201)
        staff = StaffMember.objects.get(staff_id='API-V1-APPROVAL-STAFF')
        self.assertEqual(staff.supervisor_id, self.supervisor.pk)
        self.assertEqual(staff.reporting_manager_id, self.manager.pk)
        self.assertEqual(response.data['supervisor'], self.supervisor.pk)
        self.assertEqual(response.data['reporting_manager'], self.manager.pk)

    def test_generic_assignment_approvals_require_each_approver(self):
        assignment = submit_assignment_request(self.asset, self.assignee, self.requester)
        approvals = list(assignment.approval_records.order_by('approver_id'))
        self.assertEqual(len(approvals), 2)

        client = APIClient()
        client.force_authenticate(self.manager_user)
        manager_inbox = client.get('/api/approvals/?status=pending')
        self.assertEqual(manager_inbox.status_code, 200)
        self.assertEqual([item['id'] for item in manager_inbox.data], [
            next(item.pk for item in approvals if item.approver_id == self.manager_user.pk)
        ])
        manager_approval = next(item for item in approvals if item.approver_id == self.manager_user.pk)
        response = client.post(f'/api/approvals/{manager_approval.pk}/approve/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'approved')
        self.assertEqual(response.data['acted_by'], self.manager_user.pk)
        self.asset.refresh_from_db()
        assignment.refresh_from_db()
        self.assertIsNone(self.asset.assigned_staff)
        self.assertEqual(assignment.status, 'pending')

        supervisor_approval = next(item for item in approvals if item.approver_id == self.supervisor_user.pk)
        client.force_authenticate(self.supervisor_user)
        response = client.post(f'/api/approvals/{supervisor_approval.pk}/approve/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        self.asset.refresh_from_db()
        assignment.refresh_from_db()
        self.assertEqual(self.asset.assigned_staff, self.assignee)
        self.assertEqual(assignment.status, 'approved')

    def _create_driver_request_with_two_approvers(self):
        UserRole.objects.create(user=self.requester, role='staff')
        requester_staff = StaffMember.objects.create(
            user=self.requester,
            staff_id='API-APPROVAL-REQUESTER',
            first_name='Approval',
            last_name='Requester',
            supervisor=self.supervisor,
            reporting_manager=self.manager,
        )
        client = APIClient()
        client.force_authenticate(self.requester)
        request_start = timezone.now() + timedelta(days=5)
        response = client.post('/api/driver-requests/', {
            'details': 'Multiple approver API test',
            'preferred_date': request_start.date().isoformat(),
            'requested_start': request_start.isoformat(),
            'requested_end': (request_start + timedelta(hours=1)).isoformat(),
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['requested_by'], requester_staff.pk)
        return DriverRequest.objects.get(pk=response.data['id'])

    def test_driver_request_applies_after_all_approval_records_are_approved(self):
        driver_request = self._create_driver_request_with_two_approvers()
        approvals = list(driver_request.approval_records.order_by('approver_id'))
        self.assertEqual(len(approvals), 2)

        client = APIClient()
        supervisor_approval = next(item for item in approvals if item.approver_id == self.supervisor_user.pk)
        client.force_authenticate(self.supervisor_user)
        response = client.post(f'/api/approvals/{supervisor_approval.pk}/approve/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        driver_request.refresh_from_db()
        self.assertEqual(driver_request.status, 'requested')
        self.assertIsNone(driver_request.approved_by)

        manager_approval = next(item for item in approvals if item.approver_id == self.manager_user.pk)
        client.force_authenticate(self.manager_user)
        response = client.post(f'/api/approvals/{manager_approval.pk}/approve/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        driver_request.refresh_from_db()
        self.assertEqual(driver_request.status, 'approved')
        self.assertEqual(driver_request.approved_by, self.manager_user)

    def test_rejection_cancels_other_pending_driver_approvals(self):
        driver_request = self._create_driver_request_with_two_approvers()
        approvals = list(driver_request.approval_records.order_by('approver_id'))
        supervisor_approval = next(item for item in approvals if item.approver_id == self.supervisor_user.pk)
        client = APIClient()
        client.force_authenticate(self.supervisor_user)

        response = client.post(
            f'/api/approvals/{supervisor_approval.pk}/reject/',
            {'rejection_note': 'Not approved for test'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'rejected')
        self.assertEqual(response.data['acted_by'], self.supervisor_user.pk)
        driver_request.refresh_from_db()
        self.assertEqual(driver_request.status, 'declined')
        self.assertEqual(
            driver_request.approval_records.get(approver=self.manager_user).status,
            'cancelled',
        )