from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .asset_assignment_workflow import approve_assignment_request, reject_assignment_request, submit_assignment_request
from .forms import StaffMemberForm
from .models import Asset, AssetAssignmentRequest, EquipmentTransfer, OfficeEquipment, StaffMember, UserRole


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