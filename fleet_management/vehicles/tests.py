from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import Asset, Vehicle, CompanyDocument, UserRole, StaffMember, OfficeEquipment


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


class CompanyDocumentTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='docuser', password='docpass')
        self.user_role = UserRole.objects.create(user=self.user, role='manager')
        self.user.save()

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
