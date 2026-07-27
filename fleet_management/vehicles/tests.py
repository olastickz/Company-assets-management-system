from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import Asset, Vehicle, CompanyDocument, UserRole, StaffMember, OfficeEquipment, DriverRequest


class VehicleModelTests(TestCase):
    def test_get_status_expired(self):
        vehicle = Vehicle.objects.create(
            name='Test', license_plate='TEST123', insurance_expiry=timezone.now().date() - timezone.timedelta(days=1)
        )
        self.assertEqual(vehicle.get_status('insurance_expiry'), 'expired')

    def test_get_status_expiring(self):
        vehicle = Vehicle.objects.create(
            name='Test', license_plate='TEST124', insurance_expiry=timezone.now().date() + timezone.timedelta(days=15)
        )
        self.assertEqual(vehicle.get_status('insurance_expiry'), 'expiring')

    def test_get_status_safe(self):
        vehicle = Vehicle.objects.create(
            name='Test', license_plate='TEST125', insurance_expiry=timezone.now().date() + timezone.timedelta(days=60)
        )
        self.assertEqual(vehicle.get_status('insurance_expiry'), 'safe')

    def test_get_status_unknown(self):
        vehicle = Vehicle.objects.create(
            name='Test', license_plate='TEST126', insurance_expiry=None
        )
        self.assertEqual(vehicle.get_status('insurance_expiry'), 'unknown')


class ViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.user_role = UserRole.objects.create(user=self.user, role='admin')
        self.user.save()

    def test_dashboard_redirects_without_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_loads_with_login(self):
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Assets Dashboard')

    def test_equipment_list_loads_with_login(self):
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('equipment_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Office Equipment & Laptops')

    def test_equipment_list_shows_admin_actions_for_app_admin(self):
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('equipment_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_admin'])
        self.assertContains(response, '+ Add New Equipment')
        self.assertContains(response, '📤 Bulk Upload Equipment')

    def test_equipment_create_requires_app_admin_role(self):
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('equipment_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add Equipment')

    def test_equipment_create_forbidden_for_non_admin_role(self):
        regular_user = User.objects.create_user(username='regular', password='regpass')
        UserRole.objects.create(user=regular_user, role='staff')
        self.client.login(username='regular', password='regpass')
        response = self.client.get(reverse('equipment_create'))
        self.assertEqual(response.status_code, 403)

    def test_asset_detail_shows_assigned_staff_branch_and_department(self):
        staff = StaffMember.objects.create(
            staff_id='STF005',
            first_name='Eve',
            last_name='Martin',
            department='MANAGEMENT',
            branch='LAGOS',
            is_active=True
        )
        vehicle = Vehicle.objects.create(name='Car D', license_plate='CARD01', assigned_staff=staff)
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('asset_detail', args=[vehicle.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Eve Martin')
        self.assertContains(response, 'MANAGEMENT')
        self.assertContains(response, 'LAGOS')

    def test_equipment_detail_shows_assigned_staff_branch_and_department(self):
        staff = StaffMember.objects.create(
            staff_id='STF006',
            first_name='Tom',
            last_name='Nguyen',
            department='HR',
            branch='ABUJA',
            is_active=True
        )
        equipment = OfficeEquipment.objects.create(name='Scanner A', serial_number='SCN001', assigned_staff=staff)
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('equipment_detail', args=[equipment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tom Nguyen')
        self.assertContains(response, 'HR')
        self.assertContains(response, 'ABUJA')

    def test_assigned_staff_can_report_equipment_maintenance(self):
        driver = User.objects.create_user(username='driver4', password='dpass4')
        staff = StaffMember.objects.create(
            user=driver,
            staff_id='DRV04',
            first_name='Dan',
            last_name='Miller',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=driver, role='driver')
        equipment = OfficeEquipment.objects.create(name='Assigned Projector', serial_number='PRJ001', assigned_staff=staff)

        self.client.login(username='driver4', password='dpass4')
        response = self.client.get(reverse('equipment_detail', args=[equipment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Report Fault / Request Maintenance')
        self.assertNotContains(response, '+ Add Maintenance Record')

    def test_assigned_user_can_report_equipment_maintenance_via_username(self):
        driver = User.objects.create_user(username='driver5', password='dpass5', first_name='Sam', last_name='Adams')
        UserRole.objects.create(user=driver, role='driver')
        equipment = OfficeEquipment.objects.create(
            name='Assigned Projector',
            serial_number='PRJ002',
            assigned_user='driver5'
        )

        self.client.login(username='driver5', password='dpass5')
        response = self.client.get(reverse('equipment_detail', args=[equipment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Report Fault / Request Maintenance')
        self.assertNotContains(response, '+ Add Maintenance Record')

    def test_assigned_user_can_report_equipment_maintenance_via_full_name(self):
        driver = User.objects.create_user(username='driver6', password='dpass6', first_name='Lina', last_name='Hart')
        UserRole.objects.create(user=driver, role='driver')
        equipment = OfficeEquipment.objects.create(
            name='Assigned Mouse',
            serial_number='MSH001',
            assigned_user='Lina Hart'
        )

        self.client.login(username='driver6', password='dpass6')
        response = self.client.get(reverse('equipment_detail', args=[equipment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Report Fault / Request Maintenance')
        self.assertNotContains(response, '+ Add Maintenance Record')

    def test_non_admin_document_form_hides_quick_actions(self):
        user = User.objects.create_user(username='staff2', password='spass2')
        staff = StaffMember.objects.create(
            user=user,
            staff_id='STF008',
            first_name='Jan',
            last_name='Smith',
            department='FIELD',
            branch='ABUJA',
            is_active=True
        )
        UserRole.objects.create(user=user, role='staff')

        self.client.login(username='staff2', password='spass2')
        response = self.client.get(reverse('company_document_create'))
        self.assertEqual(response.status_code, 403)

    def test_non_admin_staff_list_hides_add_staff_button(self):
        user = User.objects.create_user(username='staff3', password='spass3')
        staff = StaffMember.objects.create(
            user=user,
            staff_id='STF009',
            first_name='Mia',
            last_name='Jones',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=user, role='staff')

        self.client.login(username='staff3', password='spass3')
        response = self.client.get(reverse('staff_list'))
        self.assertEqual(response.status_code, 403)

    def test_staff_dashboard_hides_admin_create_actions(self):
        staff_user = User.objects.create_user(username='staff1', password='spass1')
        staff = StaffMember.objects.create(
            user=staff_user,
            staff_id='STF007',
            first_name='Sam',
            last_name='Worker',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=staff_user, role='staff')

        self.client.login(username='staff1', password='spass1')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Create New')
        self.assertNotContains(response, 'Bulk Import Assets')
        self.assertNotContains(response, 'Bulk Import Equipment')
        self.assertNotContains(response, 'View All Staff')
        self.assertNotContains(response, '➕ Add Vehicle Asset')
        self.assertNotContains(response, '➕ Add Equipment')
        self.assertNotContains(response, '📄 Add Document')
        self.assertNotContains(response, '📥 Import Assets')
        self.assertNotContains(response, 'My Assets')

    def test_staff_dashboard_hides_document_navigation(self):
        staff_user = User.objects.create_user(username='staff4', password='spass4')
        StaffMember.objects.create(
            user=staff_user,
            staff_id='STF010',
            first_name='Nina',
            last_name='Lee',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=staff_user, role='staff')

        self.client.login(username='staff4', password='spass4')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '📁 Documents')
        self.assertNotContains(response, reverse('company_documents_list'))

    def test_staff_dashboard_uses_assigned_work_queue_heading(self):
        staff_user = User.objects.create_user(username='staff_heading', password='spass_heading')
        StaffMember.objects.create(
            user=staff_user,
            staff_id='STF011',
            first_name='Laura',
            last_name='Miles',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=staff_user, role='staff')

        self.client.login(username='staff_heading', password='spass_heading')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Assigned Work Queue')
        self.assertContains(response, 'View only the assets assigned to you')

    def test_driver_dashboard_uses_assigned_work_queue_heading(self):
        driver = User.objects.create_user(username='driver_heading', password='dpass_heading')
        StaffMember.objects.create(
            user=driver,
            staff_id='DRV05',
            first_name='James',
            last_name='Ford',
            department='FIELD',
            branch='ABUJA',
            is_active=True
        )
        UserRole.objects.create(user=driver, role='driver')

        self.client.login(username='driver_heading', password='dpass_heading')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Assigned Work Queue')
        self.assertContains(response, 'View only the assets assigned to you')

    def test_staff_can_submit_driver_request(self):
        staff_user = User.objects.create_user(username='staff_driver', password='spass_driver')
        staff = StaffMember.objects.create(
            user=staff_user,
            staff_id='STF020',
            first_name='Clara',
            last_name='Oswald',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=staff_user, role='staff')

        self.client.login(username='staff_driver', password='spass_driver')
        response = self.client.get(reverse('driver_request_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Request Driver Support')

        response = self.client.post(reverse('driver_request_create'), {
            'details': 'Need a driver for offsite inspection',
            'preferred_date': timezone.now().date().isoformat(),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(DriverRequest.objects.count(), 1)
        request_obj = DriverRequest.objects.first()
        self.assertEqual(request_obj.requested_by, staff)
        self.assertEqual(request_obj.status, 'requested')

    def test_manager_can_assign_driver_to_request(self):
        manager_user = User.objects.create_user(username='manager_assign', password='mgrpass_assign')
        manager_staff = StaffMember.objects.create(
            user=manager_user,
            staff_id='MGR010',
            first_name='Peter',
            last_name='Quill',
            department='MANAGEMENT',
            branch='ABUJA',
            is_active=True
        )
        UserRole.objects.create(user=manager_user, role='manager')

        driver_user = User.objects.create_user(username='driver_assign', password='dpass_assign')
        driver_staff = StaffMember.objects.create(
            user=driver_user,
            staff_id='DRV07',
            first_name='Maya',
            last_name='Rossi',
            department='FIELD',
            branch='LAGOS',
            driver_status='available',
            is_active=True
        )
        UserRole.objects.create(user=driver_user, role='driver')

        request_user = User.objects.create_user(username='staff_request', password='spass_request')
        staff_request = StaffMember.objects.create(
            user=request_user,
            staff_id='STF021',
            first_name='Hannah',
            last_name='Baker',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=request_user, role='staff')

        driver_request = DriverRequest.objects.create(
            requested_by=staff_request,
            requester_user=request_user,
            details='Transfer support needed',
            status='requested'
        )

        self.client.login(username='manager_assign', password='mgrpass_assign')
        response = self.client.post(reverse('driver_request_assign', args=[driver_request.pk]), {
            'assigned_driver': driver_staff.pk,
            'notes': 'Please arrive by 10 AM',
        })
        self.assertEqual(response.status_code, 302)

        driver_request.refresh_from_db()
        driver_staff.refresh_from_db()
        self.assertEqual(driver_request.status, 'assigned')
        self.assertEqual(driver_request.assigned_driver, driver_staff)
        self.assertEqual(driver_staff.driver_status, 'unavailable')

    def test_manager_can_reassign_driver_and_restore_previous_driver(self):
        manager_user = User.objects.create_user(username='manager_reassign', password='mgrpass_reassign')
        manager_staff = StaffMember.objects.create(
            user=manager_user,
            staff_id='MGR011',
            first_name='Carol',
            last_name='Marcus',
            department='MANAGEMENT',
            branch='ABUJA',
            is_active=True
        )
        UserRole.objects.create(user=manager_user, role='manager')

        original_driver_user = User.objects.create_user(username='driver_orig', password='dpass_orig')
        original_driver = StaffMember.objects.create(
            user=original_driver_user,
            staff_id='DRV08',
            first_name='Rory',
            last_name='Williams',
            department='FIELD',
            branch='LAGOS',
            driver_status='unavailable',
            is_active=True
        )
        UserRole.objects.create(user=original_driver_user, role='driver')

        new_driver_user = User.objects.create_user(username='driver_new', password='dpass_new')
        new_driver = StaffMember.objects.create(
            user=new_driver_user,
            staff_id='DRV09',
            first_name='Clara',
            last_name='Oswald',
            department='FIELD',
            branch='LAGOS',
            driver_status='available',
            is_active=True
        )
        UserRole.objects.create(user=new_driver_user, role='driver')

        request_user = User.objects.create_user(username='staff_reassign', password='spass_reassign')
        staff_request = StaffMember.objects.create(
            user=request_user,
            staff_id='STF024',
            first_name='Amy',
            last_name='Pond',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=request_user, role='staff')

        driver_request = DriverRequest.objects.create(
            requested_by=staff_request,
            requester_user=request_user,
            details='Urgent route support',
            status='assigned',
            assigned_driver=original_driver,
            assigned_by=manager_user,
            assigned_at=timezone.now(),
        )

        self.client.login(username='manager_reassign', password='mgrpass_reassign')
        response = self.client.post(reverse('driver_request_assign', args=[driver_request.pk]), {
            'assigned_driver': new_driver.pk,
            'notes': 'Switching to a closer driver',
        })
        self.assertEqual(response.status_code, 302)

        driver_request.refresh_from_db()
        original_driver.refresh_from_db()
        new_driver.refresh_from_db()
        self.assertEqual(driver_request.assigned_driver, new_driver)
        self.assertEqual(new_driver.driver_status, 'unavailable')
        self.assertEqual(original_driver.driver_status, 'available')

    def test_driver_request_detail_restricts_access_for_other_staff(self):
        staff_request = User.objects.create_user(username='staff_owner', password='spass_owner')
        staff_owner = StaffMember.objects.create(
            user=staff_request,
            staff_id='STF022',
            first_name='Rita',
            last_name='Hayworth',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=staff_request, role='staff')

        other_staff_user = User.objects.create_user(username='other_staff', password='spass_other')
        StaffMember.objects.create(
            user=other_staff_user,
            staff_id='STF023',
            first_name='Jack',
            last_name='Shephard',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=other_staff_user, role='staff')

        driver_request = DriverRequest.objects.create(
            requested_by=staff_owner,
            requester_user=staff_request,
            details='Need route support',
            status='requested'
        )

        self.client.login(username='other_staff', password='spass_other')
        response = self.client.get(reverse('driver_request_detail', args=[driver_request.pk]))
        self.assertEqual(response.status_code, 403)

    def test_staff_base_navigation_hides_documents_link(self):
        staff_user = User.objects.create_user(username='staff5', password='spass5')
        StaffMember.objects.create(
            user=staff_user,
            staff_id='STF011',
            first_name='Nora',
            last_name='Park',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=staff_user, role='staff')

        self.client.login(username='staff5', password='spass5')
        response = self.client.get(reverse('equipment_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Documents')
        self.assertNotContains(response, reverse('company_documents_list'))

    def test_staff_cannot_access_company_documents_list(self):
        staff_user = User.objects.create_user(username='staff6', password='spass6')
        StaffMember.objects.create(
            user=staff_user,
            staff_id='STF012',
            first_name='Matt',
            last_name='Green',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=staff_user, role='staff')

        self.client.login(username='staff6', password='spass6')
        response = self.client.get(reverse('company_documents_list'))
        self.assertEqual(response.status_code, 403)

    def test_staff_cannot_access_company_documents_data(self):
        staff_user = User.objects.create_user(username='staff7', password='spass7')
        StaffMember.objects.create(
            user=staff_user,
            staff_id='STF013',
            first_name='Ike',
            last_name='Thomas',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=staff_user, role='staff')

        self.client.login(username='staff7', password='spass7')
        response = self.client.get(reverse('company_documents_data'))
        self.assertEqual(response.status_code, 403)

    def test_staff_cannot_access_company_documents_counts(self):
        staff_user = User.objects.create_user(username='staff8', password='spass8')
        StaffMember.objects.create(
            user=staff_user,
            staff_id='STF014',
            first_name='Zoe',
            last_name='Wong',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=staff_user, role='staff')

        self.client.login(username='staff8', password='spass8')
        response = self.client.get(reverse('company_documents_counts'))
        self.assertEqual(response.status_code, 403)

    def test_staff_cannot_create_company_document(self):
        staff_user = User.objects.create_user(username='staff9', password='spass9')
        StaffMember.objects.create(
            user=staff_user,
            staff_id='STF015',
            first_name='Sam',
            last_name='Taylor',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=staff_user, role='staff')

        self.client.login(username='staff9', password='spass9')
        response = self.client.get(reverse('company_document_create'))
        self.assertEqual(response.status_code, 403)

        response = self.client.post(reverse('company_document_create'), {
            'name': 'Staff Doc',
            'document_type': 'policy',
        })
        self.assertEqual(response.status_code, 403)

    def test_manager_cannot_create_company_document(self):
        manager_user = User.objects.create_user(username='mgr2', password='mgrpass2')
        StaffMember.objects.create(
            user=manager_user,
            staff_id='MGR002',
            first_name='Mona',
            last_name='Green',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=manager_user, role='manager')

        self.client.login(username='mgr2', password='mgrpass2')
        response = self.client.get(reverse('company_document_create'))
        self.assertEqual(response.status_code, 403)

        response = self.client.post(reverse('company_document_create'), {
            'name': 'Manager Doc',
            'document_type': 'policy',
        })
        self.assertEqual(response.status_code, 403)

    def test_company_document_capability_flags_are_exposed_in_context(self):
        manager_user = User.objects.create_user(username='mgr3', password='mgrpass3')
        StaffMember.objects.create(
            user=manager_user,
            staff_id='MGR003',
            first_name='Mina',
            last_name='Stone',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=manager_user, role='manager')

        self.client.login(username='mgr3', password='mgrpass3')
        response = self.client.get(reverse('company_documents_list'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_view_company_documents'])
        self.assertTrue(response.context['can_create_company_documents'])

    def test_staff_cannot_delete_company_document(self):
        staff_user = User.objects.create_user(username='staff7', password='spass7')
        StaffMember.objects.create(
            user=staff_user,
            staff_id='STF013',
            first_name='Ike',
            last_name='Thomas',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=staff_user, role='staff')
        document = CompanyDocument.objects.create(
            name='Test Doc',
            document_type='policy',
            expiry_date=timezone.now().date() + timezone.timedelta(days=30),
            created_by=self.user
        )

        self.client.login(username='staff7', password='spass7')
        response = self.client.post(reverse('company_document_delete', args=[document.pk]))
        self.assertEqual(response.status_code, 403)

    def test_dashboard_filters_by_assigned_staff_branch_and_department(self):
        staff1 = StaffMember.objects.create(
            staff_id='S001',
            first_name='Alice',
            last_name='Anderson',
            department='ABS',
            branch='LAGOS',
        )
        staff2 = StaffMember.objects.create(
            staff_id='S002',
            first_name='Bob',
            last_name='Brown',
            department='HR',
            branch='ABUJA',
        )
        Vehicle.objects.create(name='Car A', license_plate='CARA01', assigned_staff=staff1)
        OfficeEquipment.objects.create(name='Laptop B', serial_number='SN123', assigned_staff=staff2)

        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('dashboard') + f'?assigned_staff={staff1.id}')
        self.assertContains(response, 'Car A')
        self.assertNotContains(response, 'Laptop B')

        response = self.client.get(reverse('dashboard') + '?department=ABS')
        self.assertContains(response, 'Car A')
        self.assertNotContains(response, 'Laptop B')

        response = self.client.get(reverse('dashboard') + '?branch=ABUJA')
        self.assertContains(response, 'Laptop B')
        self.assertNotContains(response, 'Car A')

    def test_export_vehicles_csv(self):
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('export_vehicles_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('Name,Make,Model,VIN,License Plate', response.content.decode('utf-8'))

    def test_export_vehicles_excel(self):
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('export_vehicles_excel'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    def test_activity_dashboard_requires_login(self):
        response = self.client.get(reverse('activity_dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_activity_dashboard_with_login(self):
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('activity_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'User Activity Dashboard')

    def test_api_vehicle_list_requires_login(self):
        response = self.client.get(reverse('vehicle-list'))
        # DRF returns 401 Unauthorized when no credentials provided
        self.assertEqual(response.status_code, 401)

    def test_api_vehicle_list_with_login(self):
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('vehicle-list'))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_release_vehicle_assignment_unassigns_staff(self):
        staff = StaffMember.objects.create(
            staff_id='STF003',
            first_name='Mark',
            last_name='Taylor',
            is_active=True
        )
        vehicle = Vehicle.objects.create(name='Car C', license_plate='CARC01', assigned_staff=staff)
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(reverse('asset_release', args=[vehicle.pk]), {
            'back_url': reverse('asset_detail', args=[vehicle.pk])
        })
        self.assertEqual(response.status_code, 302)
        vehicle.refresh_from_db()
        self.assertIsNone(vehicle.assigned_staff)
        self.assertIsNone(vehicle.asset.assigned_staff)

    def test_release_equipment_assignment_unassigns_staff(self):
        staff = StaffMember.objects.create(
            staff_id='STF004',
            first_name='Lisa',
            last_name='Chen',
            is_active=True
        )
        equipment = OfficeEquipment.objects.create(name='Printer A', serial_number='PRT001', assigned_staff=staff)
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(reverse('equipment_release', args=[equipment.pk]), {
            'back_url': reverse('equipment_detail', args=[equipment.pk])
        })
        self.assertEqual(response.status_code, 302)
        equipment.refresh_from_db()
        self.assertIsNone(equipment.assigned_staff)
        self.assertIsNone(equipment.asset.assigned_staff)

    def test_manager_dashboard_shows_all_departments(self):
        # Managers should see all assets across departments by default
        manager = User.objects.create_user(username='mgr', password='mgrpass')
        UserRole.objects.create(user=manager, role='manager', department='HR')

        staff_hr = StaffMember.objects.create(
            staff_id='HR001', first_name='Helen', last_name='Ray', department='HR', branch='LAGOS', is_active=True
        )
        staff_it = StaffMember.objects.create(
            staff_id='IT001', first_name='Ian', last_name='Curtis', department='ITECO', branch='ABUJA', is_active=True
        )

        Vehicle.objects.create(name='HR Car', license_plate='HRC01', assigned_staff=staff_hr)
        Vehicle.objects.create(name='Other Car', license_plate='OTC01', assigned_staff=staff_it)

        self.client.login(username='mgr', password='mgrpass')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'HR Car')
        self.assertContains(response, 'Other Car')

    def test_driver_my_assets_redirects_to_dashboard(self):
        driver = User.objects.create_user(username='driver1', password='dpass')
        staff = StaffMember.objects.create(
            user=driver, staff_id='DRV01', first_name='Dave', last_name='Driver', department='DRIVE', branch='LAGOS', is_active=True
        )
        UserRole.objects.create(user=driver, role='driver')
        Vehicle.objects.create(name='Driver Car', license_plate='DRVC01', assigned_staff=staff)

        self.client.login(username='driver1', password='dpass')
        response = self.client.get(reverse('my_assets'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Driver Car')

    def test_driver_equipment_list_scopes_to_assigned_equipment(self):
        driver = User.objects.create_user(username='driver3', password='dpass3')
        staff = StaffMember.objects.create(
            user=driver, staff_id='DRV03', first_name='Dana', last_name='Driver', department='DRIVE', branch='LAGOS', is_active=True
        )
        other_staff = StaffMember.objects.create(
            staff_id='OTH02', first_name='Other', last_name='Member', department='HR', branch='ABUJA', is_active=True
        )
        UserRole.objects.create(user=driver, role='driver')
        OfficeEquipment.objects.create(name='Assigned Tablet', serial_number='TAB001', assigned_staff=staff)
        OfficeEquipment.objects.create(name='Other Printer', serial_number='PRT002', assigned_staff=other_staff)

        self.client.login(username='driver3', password='dpass3')
        response = self.client.get(reverse('equipment_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Assigned Tablet')
        self.assertNotContains(response, 'Other Printer')

    def test_driver_without_staff_profile_sees_no_unscoped_equipment(self):
        driver = User.objects.create_user(username='driver_no_profile', password='dpass_np')
        UserRole.objects.create(user=driver, role='driver')
        OfficeEquipment.objects.create(name='Company Printer', serial_number='CPR001', assigned_user='someone_else', equipment_type='printer', regional_office='Lagos')

        self.client.login(username='driver_no_profile', password='dpass_np')
        response = self.client.get(reverse('equipment_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Company Printer')
        self.assertEqual(response.context['total_equipment'], 0)
        self.assertEqual(response.context['regional_office_counts']['Lagos'], 0)
        self.assertEqual(response.context['equipment_type_counts']['printer'], 0)

    def test_driver_dashboard_scopes_to_assigned_vehicle_documents_only(self):
        driver = User.objects.create_user(username='driver2', password='dpass2')
        staff = StaffMember.objects.create(
            user=driver, staff_id='DRV02', first_name='Dora', last_name='Driver', department='DRIVE', branch='LAGOS', is_active=True
        )
        other_staff = StaffMember.objects.create(
            staff_id='OTH01', first_name='Other', last_name='Staff', department='HR', branch='ABUJA', is_active=True
        )
        UserRole.objects.create(user=driver, role='driver')
        assigned_vehicle = Vehicle.objects.create(name='Assigned Car', license_plate='ASGD01', assigned_staff=staff)
        OfficeEquipment.objects.create(name='Assigned Laptop', serial_number='LPT001', assigned_staff=staff)
        CompanyDocument.objects.create(
            name='Assigned Vehicle Doc', document_type='contract', issue_date=timezone.now().date(), expiry_date=timezone.now().date() + timezone.timedelta(days=30), notify_days_before=15,
            related_vehicle=assigned_vehicle
        )
        other_vehicle = Vehicle.objects.create(name='Other Car', license_plate='OTHR01', assigned_staff=other_staff)
        other_equipment = OfficeEquipment.objects.create(name='Other Equipment', serial_number='OTH002', assigned_staff=other_staff)
        CompanyDocument.objects.create(
            name='Other Vehicle Doc', document_type='insurance', issue_date=timezone.now().date(), expiry_date=timezone.now().date() + timezone.timedelta(days=30), notify_days_before=15,
            related_vehicle=other_vehicle
        )
        CompanyDocument.objects.create(
            name='Other Responsible Doc', document_type='insurance', issue_date=timezone.now().date(), expiry_date=timezone.now().date() + timezone.timedelta(days=30), notify_days_before=15,
            responsible_staff=other_staff
        )
        CompanyDocument.objects.create(
            name='Other Equipment Doc', document_type='insurance', issue_date=timezone.now().date(), expiry_date=timezone.now().date() + timezone.timedelta(days=30), notify_days_before=15,
            related_equipment=other_equipment
        )

        self.client.login(username='driver2', password='dpass2')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Assigned Car')
        self.assertContains(response, 'Assigned Laptop')
        self.assertContains(response, 'Assigned Vehicle Doc')
        self.assertNotContains(response, 'Other Car')
        self.assertNotContains(response, 'Other Vehicle Doc')
        self.assertNotContains(response, 'Other Responsible Doc')
        self.assertNotContains(response, 'Other Equipment Doc')


class CompanyDocumentTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='docuser', password='docpass')
        self.user_role = UserRole.objects.create(user=self.user, role='manager')
        self.user.save()

    def test_vehicle_scope_requires_related_vehicle(self):
        self.client.login(username='docuser', password='docpass')
        response = self.client.post(reverse('company_document_create'), {
            'name': 'Missing Vehicle Link',
            'document_type': 'insurance',
            'issue_date': (timezone.now().date() - timezone.timedelta(days=30)).strftime('%Y-%m-%d'),
            'expiry_date': (timezone.now().date() + timezone.timedelta(days=180)).strftime('%Y-%m-%d'),
            'notify_days_before': '30',
            'document_scope': 'vehicle',
            'status': 'active',
        })

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIn('related_vehicle', form.errors)
        self.assertIn('Please select a vehicle asset for vehicle documents.', form.errors['related_vehicle'])

    def test_driver_can_view_assigned_vehicle_document_detail(self):
        driver = User.objects.create_user(username='driver_doc', password='dpass_doc')
        staff = StaffMember.objects.create(
            user=driver,
            staff_id='DRV10',
            first_name='Derek',
            last_name='Driver',
            department='DRIVE',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=driver, role='driver')
        assigned_vehicle = Vehicle.objects.create(name='Assigned Detail Car', license_plate='ADOC01', assigned_staff=staff)
        document = CompanyDocument.objects.create(
            name='Driver Assigned Doc',
            document_type='insurance',
            issue_date=timezone.now().date(),
            expiry_date=timezone.now().date() + timezone.timedelta(days=30),
            notify_days_before=15,
            related_vehicle=assigned_vehicle,
        )

        self.client.login(username='driver_doc', password='dpass_doc')
        response = self.client.get(reverse('company_document_detail', args=[document.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Driver Assigned Doc')

    def test_driver_cannot_view_other_vehicle_document_detail(self):
        driver = User.objects.create_user(username='driver_doc2', password='dpass_doc2')
        staff = StaffMember.objects.create(
            user=driver,
            staff_id='DRV11',
            first_name='Drew',
            last_name='Driver',
            department='DRIVE',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=driver, role='driver')
        other_vehicle = Vehicle.objects.create(name='Other Detail Car', license_plate='ODOC01')
        document = CompanyDocument.objects.create(
            name='Other Vehicle Doc',
            document_type='insurance',
            issue_date=timezone.now().date(),
            expiry_date=timezone.now().date() + timezone.timedelta(days=30),
            notify_days_before=15,
            related_vehicle=other_vehicle,
        )

        self.client.login(username='driver_doc2', password='dpass_doc2')
        response = self.client.get(reverse('company_document_detail', args=[document.pk]))
        self.assertEqual(response.status_code, 403)

    def test_staff_cannot_view_vehicle_document_detail(self):
        staff_user = User.objects.create_user(username='staff_doc', password='spass_doc')
        staff = StaffMember.objects.create(
            user=staff_user,
            staff_id='STF020',
            first_name='Sam',
            last_name='Staff',
            department='FIELD',
            branch='LAGOS',
            is_active=True
        )
        UserRole.objects.create(user=staff_user, role='staff')
        vehicle = Vehicle.objects.create(name='Staff Detail Car', license_plate='SDOC01', assigned_staff=staff)
        document = CompanyDocument.objects.create(
            name='Staff Assigned Doc',
            document_type='insurance',
            issue_date=timezone.now().date(),
            expiry_date=timezone.now().date() + timezone.timedelta(days=30),
            notify_days_before=15,
            related_vehicle=vehicle,
        )

        self.client.login(username='staff_doc', password='spass_doc')
        response = self.client.get(reverse('company_document_detail', args=[document.pk]))
        self.assertEqual(response.status_code, 403)

    def test_get_status_returns_expired(self):
        document = CompanyDocument.objects.create(
            name='Expired Doc',
            document_type='contract',
            issue_date=timezone.now().date() - timezone.timedelta(days=365),
            expiry_date=timezone.now().date() - timezone.timedelta(days=1),
            notify_days_before=30,
        )
        self.assertEqual(document.get_status(), 'expired')

    def test_get_status_returns_expiring(self):
        document = CompanyDocument.objects.create(
            name='Warning Doc',
            document_type='policy',
            issue_date=timezone.now().date() - timezone.timedelta(days=30),
            expiry_date=timezone.now().date() + timezone.timedelta(days=10),
            notify_days_before=15,
        )
        self.assertEqual(document.get_status(), 'expiring')

    def test_get_status_returns_safe(self):
        document = CompanyDocument.objects.create(
            name='Safe Doc',
            document_type='policy',
            issue_date=timezone.now().date() - timezone.timedelta(days=30),
            expiry_date=timezone.now().date() + timezone.timedelta(days=90),
            notify_days_before=30,
        )
        self.assertEqual(document.get_status(), 'safe')

    def test_company_documents_list_filters_by_status(self):
        self.client.login(username='docuser', password='docpass')
        CompanyDocument.objects.create(
            name='Expired Doc',
            document_type='contract',
            issue_date=timezone.now().date() - timezone.timedelta(days=365),
            expiry_date=timezone.now().date() - timezone.timedelta(days=1),
            notify_days_before=30,
        )
        CompanyDocument.objects.create(
            name='Expiring Doc',
            document_type='policy',
            issue_date=timezone.now().date() - timezone.timedelta(days=30),
            expiry_date=timezone.now().date() + timezone.timedelta(days=10),
            notify_days_before=15,
        )
        CompanyDocument.objects.create(
            name='Safe Doc',
            document_type='policy',
            issue_date=timezone.now().date() - timezone.timedelta(days=30),
            expiry_date=timezone.now().date() + timezone.timedelta(days=90),
            notify_days_before=30,
        )

        response = self.client.get(reverse('company_documents_list') + '?status=expired')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['documents']), 1)
        self.assertEqual(response.context['documents'][0].name, 'Expired Doc')

    def test_company_documents_list_searches_text(self):
        self.client.login(username='docuser', password='docpass')
        CompanyDocument.objects.create(
            name='Audit Report',
            document_type='policy',
            issue_date=timezone.now().date() - timezone.timedelta(days=30),
            expiry_date=timezone.now().date() + timezone.timedelta(days=40),
            notify_days_before=15,
        )
        response = self.client.get(reverse('company_documents_list') + '?search=audit')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['documents']), 1)
        self.assertEqual(response.context['documents'][0].name, 'Audit Report')

    def test_vehicle_assigned_staff_property(self):
        staff = StaffMember.objects.create(
            staff_id='STF001',
            first_name='Jane',
            last_name='Doe',
            is_active=True
        )
        vehicle = Vehicle.objects.create(name='Car A', license_plate='CARA01', assigned_staff=staff)
        self.assertEqual(vehicle.assigned_to_display, str(staff))

    def test_company_document_can_link_to_vehicle_and_equipment(self):
        vehicle = Vehicle.objects.create(name='Car B', license_plate='CARB01')
        equipment = OfficeEquipment.objects.create(name='Laptop A', equipment_type='laptop')
        document = CompanyDocument.objects.create(
            name='Vehicle Insur',
            document_type='insurance',
            issue_date=timezone.now().date(),
            expiry_date=timezone.now().date() + timezone.timedelta(days=365),
            notify_days_before=30,
            related_vehicle=vehicle,
        )
        self.assertEqual(document.asset_display, str(vehicle.asset))
        self.assertEqual(document.asset_type, 'vehicle')

        document.related_vehicle = None
        document.related_equipment = equipment
        document.save()
        self.assertEqual(document.asset_display, str(equipment.asset))
        self.assertEqual(document.asset_type, 'equipment')

    def test_company_document_can_link_to_shared_asset(self):
        staff = StaffMember.objects.create(
            staff_id='STF002',
            first_name='Ann',
            last_name='Smith',
            is_active=True
        )
        asset = Asset.objects.create(
            name='Shared Maintenance Unit',
            asset_type='equipment',
            status='active',
            assigned_staff=staff
        )
        document = CompanyDocument.objects.create(
            name='Direct Asset Doc',
            document_type='insurance',
            issue_date=timezone.now().date(),
            expiry_date=timezone.now().date() + timezone.timedelta(days=180),
            notify_days_before=30,
            related_asset=asset,
        )
        self.assertEqual(document.asset_display, str(asset))
        self.assertEqual(document.asset_type, 'equipment')

    def test_company_documents_list_searches_linked_assets(self):
        self.client.login(username='docuser', password='docpass')
        vehicle = Vehicle.objects.create(name='Search Car', license_plate='SEARC01')
        CompanyDocument.objects.create(
            name='Searchable Vehicle Doc',
            document_type='insurance',
            issue_date=timezone.now().date(),
            expiry_date=timezone.now().date() + timezone.timedelta(days=40),
            notify_days_before=15,
            related_vehicle=vehicle,
        )
        response = self.client.get(reverse('company_documents_list') + '?search=search car')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['documents']), 1)
        self.assertEqual(response.context['documents'][0].name, 'Searchable Vehicle Doc')
