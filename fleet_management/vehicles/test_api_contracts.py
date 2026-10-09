from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import (
    Asset,
    CompanyDocument,
    DriverRequest,
    EmailDeliveryLog,
    EquipmentTransfer,
    EquipmentWorkOrder,
    MaintenanceItem,
    OfficeEquipment,
    StaffMember,
    UserRole,
    Vehicle,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class WorkOrderApiContractTests(TestCase):
    def test_manager_can_create_read_update_and_delete_work_order(self):
        manager = User.objects.create_user(username='work-order-api-manager', password='manager-pass')
        UserRole.objects.create(user=manager, role='manager')
        equipment = OfficeEquipment.objects.create(name='Work Order API Equipment')
        client = APIClient()
        client.force_authenticate(manager)

        create_response = client.post('/api/equipment-work-orders/', {
            'equipment': equipment.pk,
            'work_type': 'repair',
            'title': 'API repair order',
            'description': 'Created through the API',
            'priority': 'high',
        }, format='json')
        self.assertEqual(create_response.status_code, 201)
        work_order_id = create_response.data['id']
        self.assertEqual(client.get(f'/api/equipment-work-orders/{work_order_id}/').status_code, 200)

        update_response = client.patch(
            f'/api/equipment-work-orders/{work_order_id}/', {'status': 'completed'}, format='json'
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.data['status'], 'completed')
        self.assertEqual(client.delete(f'/api/equipment-work-orders/{work_order_id}/').status_code, 204)


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminApiContractTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='api-contract-admin', password='admin-pass')
        UserRole.objects.create(user=self.admin, role='admin')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_admin_staff_creation_requires_email_for_setup_link(self):
        response = self.client.post('/api/v1/admin/staff/', {
            'staff_id': 'API-V1-NO-EMAIL',
            'first_name': 'No',
            'last_name': 'Email',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.data)
        self.assertFalse(StaffMember.objects.filter(staff_id='API-V1-NO-EMAIL').exists())

    def test_admin_can_create_read_update_and_delete_staff_directory_record(self):
        create_response = self.client.post('/api/v1/admin/staff/', {
            'staff_id': 'API-V1-STAFF',
            'first_name': 'Directory',
            'last_name': 'Entry',
            'email': 'api-v1-staff@example.invalid',
            'is_active': True,
        }, format='json')
        self.assertEqual(create_response.status_code, 201)
        staff_id = create_response.data['id']

        detail_response = self.client.get(f'/api/v1/admin/staff/{staff_id}/')
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data['staff_id'], 'API-V1-STAFF')

        update_response = self.client.patch(
            f'/api/v1/admin/staff/{staff_id}/', {'department': 'ABS'}, format='json'
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.data['department'], 'ABS')
        self.assertEqual(self.client.delete(f'/api/v1/admin/staff/{staff_id}/').status_code, 204)

    def test_admin_can_send_notifications_and_retry_delivery(self):
        with patch('vehicles.api_v1.send_expiry_alerts', return_value={'status': 'sent', 'sent_count': 0}):
            send_response = self.client.post('/api/v1/notifications/send-now/', {}, format='json')
        self.assertEqual(send_response.status_code, 200)
        self.assertEqual(send_response.data, {'status': 'sent', 'sent_count': 0})

        delivery = EmailDeliveryLog.objects.create(
            recipient_email='retry-api-test@example.com',
            subject='API retry test',
            status='failed',
            error_message='test failure',
        )
        retry_response = self.client.post(
            f'/api/v1/notifications/deliveries/{delivery.pk}/retry/', {}, format='json'
        )
        self.assertEqual(retry_response.status_code, 200)
        self.assertEqual(retry_response.data, {'id': delivery.pk, 'status': 'queued'})
        delivery.refresh_from_db()
        self.assertIsNone(delivery.error_message)


@override_settings(SECURE_SSL_REDIRECT=False)
class CoreResourceApiContractTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='resource-api-admin', password='admin-pass')
        UserRole.objects.create(user=self.admin, role='admin')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_vehicle_and_equipment_crud(self):
        vehicle_response = self.client.post('/api/vehicles/', {
            'name': 'API Vehicle',
            'license_plate': 'API-VEHICLE-1',
            'asset_type': 'van',
        }, format='json')
        self.assertEqual(vehicle_response.status_code, 201)
        vehicle_id = vehicle_response.data['id']
        self.assertEqual(self.client.get(f'/api/vehicles/{vehicle_id}/').status_code, 200)

        vehicle_update = self.client.patch(
            f'/api/vehicles/{vehicle_id}/', {'name': 'Updated API Vehicle'}, format='json'
        )
        self.assertEqual(vehicle_update.status_code, 200)
        self.assertEqual(vehicle_update.data['name'], 'Updated API Vehicle')
        self.assertEqual(self.client.delete(f'/api/vehicles/{vehicle_id}/').status_code, 204)

        equipment_response = self.client.post('/api/equipment/', {
            'name': 'API Equipment',
            'equipment_type': 'laptop',
            'quantity': 1,
        }, format='json')
        self.assertEqual(equipment_response.status_code, 201)
        equipment_id = equipment_response.data['id']
        self.assertEqual(self.client.get(f'/api/equipment/{equipment_id}/').status_code, 200)

        equipment_update = self.client.patch(
            f'/api/equipment/{equipment_id}/', {'location': 'Lagos Office'}, format='json'
        )
        self.assertEqual(equipment_update.status_code, 200)
        self.assertEqual(equipment_update.data['location'], 'Lagos Office')
        self.assertEqual(self.client.delete(f'/api/equipment/{equipment_id}/').status_code, 204)

    def test_staff_and_document_crud(self):
        staff_response = self.client.post('/api/staff/', {
            'staff_id': 'API-STAFF-CRUD',
            'first_name': 'API',
            'last_name': 'Staff',
        }, format='json')
        self.assertEqual(staff_response.status_code, 201)
        staff_id = staff_response.data['id']
        self.assertEqual(self.client.get(f'/api/staff/{staff_id}/').status_code, 200)

        staff_update = self.client.put(
            f'/api/staff/{staff_id}/', {'first_name': 'Updated'}, format='json'
        )
        self.assertEqual(staff_update.status_code, 200)
        self.assertEqual(staff_update.data['first_name'], 'Updated')
        self.assertEqual(self.client.delete(f'/api/staff/{staff_id}/').status_code, 204)

        document_response = self.client.post('/api/documents/', {
            'name': 'API Document',
            'document_type': 'other',
            'expiry_date': '2027-01-01',
        }, format='json')
        self.assertEqual(document_response.status_code, 201)
        document_id = document_response.data['id']
        self.assertEqual(self.client.get(f'/api/documents/{document_id}/').status_code, 200)

        document_update = self.client.patch(
            f'/api/documents/{document_id}/', {'name': 'Updated API Document'}, format='json'
        )
        self.assertEqual(document_update.status_code, 200)
        self.assertEqual(document_update.data['name'], 'Updated API Document')
        self.assertEqual(self.client.delete(f'/api/documents/{document_id}/').status_code, 204)

    def test_document_api_accepts_multipart_file_upload(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            upload = SimpleUploadedFile(
                'api-document.txt', b'API upload fixture', content_type='text/plain'
            )
            response = self.client.post('/api/documents/', {
                'name': 'Multipart API Document',
                'document_type': 'other',
                'expiry_date': '2027-01-01',
                'document_file': upload,
            }, format='multipart')

            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.data['name'], 'Multipart API Document')
            document = CompanyDocument.objects.get(pk=response.data['id'])
            self.assertTrue(document.document_file.name.endswith('api-document.txt'))

    def test_asset_assignment_and_equipment_maintenance_crud(self):
        staff = StaffMember.objects.create(
            staff_id='API-ASSIGNEE-1', first_name='API', last_name='Assignee'
        )
        asset = Asset.objects.create(name='API Assignable Asset')
        assign_response = self.client.post(
            f'/api/asset/{asset.pk}/assign/', {'staff_id': staff.pk}, format='json'
        )
        self.assertEqual(assign_response.status_code, 200)
        self.assertEqual(assign_response.data['asset']['assigned_staff'], staff.pk)
        self.assertEqual(len(self.client.get(f'/api/asset/{asset.pk}/history/').data), 1)

        release_response = self.client.post(f'/api/asset/{asset.pk}/release/')
        self.assertEqual(release_response.status_code, 200)
        self.assertIsNone(release_response.data['asset']['assigned_staff'])
        asset_update = self.client.put(
            f'/api/asset/{asset.pk}/', {'name': 'Updated API Asset'}, format='json'
        )
        self.assertEqual(asset_update.status_code, 200)
        self.assertEqual(asset_update.data['name'], 'Updated API Asset')
        self.assertEqual(self.client.delete(f'/api/asset/{asset.pk}/').status_code, 204)

        equipment = OfficeEquipment.objects.create(name='Maintenance API Equipment')
        maintenance_response = self.client.post('/api/equipment-maintenance/', {
            'equipment': equipment.pk,
            'description': 'Quarterly service',
            'due_date': '2027-01-15',
            'cost': '100.00',
        }, format='json')
        self.assertEqual(maintenance_response.status_code, 201)
        maintenance_id = maintenance_response.data['id']
        self.assertEqual(self.client.get('/api/equipment-maintenance/').status_code, 200)

        maintenance_update = self.client.patch(
            f'/api/equipment-maintenance/{maintenance_id}/',
            {'notes': 'Completed'},
            format='json',
        )
        self.assertEqual(maintenance_update.status_code, 200)
        self.assertEqual(maintenance_update.data['notes'], 'Completed')
        self.assertEqual(
            self.client.delete(f'/api/equipment-maintenance/{maintenance_id}/').status_code,
            204,
        )

    def test_bulk_upload_apis_return_json_for_missing_files(self):
        for path in ('/api/bulk-upload-assets/', '/api/bulk-upload-equipment/'):
            with self.subTest(path=path):
                response = self.client.post(path, {}, format='multipart')
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response['Content-Type'], 'application/json')
                self.assertIn('detail', response.data)

    def test_bulk_upload_apis_import_csv_and_report_counts(self):
        vehicle_csv = SimpleUploadedFile(
            'vehicles.csv',
            b'name,license_plate,make,model,vehicle_type\nAPI Import Vehicle,API-IMPORT-1,Toyota,Hiace,van\n',
            content_type='text/csv',
        )
        vehicle_response = self.client.post(
            '/api/bulk-upload-assets/', {'csv_file': vehicle_csv}, format='multipart'
        )
        self.assertEqual(vehicle_response.status_code, 200)
        self.assertEqual(vehicle_response.data, {'created': 1, 'failed': 0, 'errors': []})
        self.assertTrue(Vehicle.objects.filter(license_plate='API-IMPORT-1').exists())

        equipment_csv = SimpleUploadedFile(
            'equipment.csv',
            b'name,equipment_type,serial_number,quantity\nAPI Import Laptop,laptop,API-IMPORT-SN,1\n',
            content_type='text/csv',
        )
        equipment_response = self.client.post(
            '/api/bulk-upload-equipment/', {'csv_file': equipment_csv}, format='multipart'
        )
        self.assertEqual(equipment_response.status_code, 200)
        self.assertEqual(equipment_response.data, {'created': 1, 'failed': 0, 'errors': []})
        self.assertTrue(OfficeEquipment.objects.filter(serial_number='API-IMPORT-SN').exists())

    def test_token_password_reset_and_export_routes(self):
        token_user = User.objects.create_user(
            username='token-api-user', password='token-pass', email='token-api@example.com'
        )
        token_response = APIClient().post('/api/get-token/', {
            'username': token_user.username,
            'password': 'token-pass',
        }, format='json')
        self.assertEqual(token_response.status_code, 200)
        self.assertTrue(token_response.data['token'])

        reset_response = APIClient().post(
            '/api/password-reset/', {'email': 'missing-user@example.com'}, format='json'
        )
        self.assertEqual(reset_response.status_code, 200)
        self.assertIn('detail', reset_response.data)

        self.assertTrue(self.client.get('/api/export/vehicles/csv/')['Content-Type'].startswith('text/csv'))
        self.assertTrue(self.client.get('/api/export/equipment/csv/')['Content-Type'].startswith('text/csv'))


@override_settings(SECURE_SSL_REDIRECT=False)
class VersionedReadApiContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.manager = User.objects.create_user(username='api-contract-manager', password='manager-pass')
        UserRole.objects.create(user=self.manager, role='manager')
        self.client.force_authenticate(self.manager)

    def test_reports_and_read_only_settings_return_expected_json(self):
        for path in (
            '/api/v1/reports/overview/',
            '/api/v1/reports/vehicles/',
            '/api/v1/reports/equipment/',
            '/api/v1/reports/documents/',
            '/api/v1/reports/maintenance/',
            '/api/v1/reports/transfers/',
            '/api/v1/reports/audit/?page_size=1',
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIsInstance(response.data, dict)

        overview = self.client.get('/api/v1/reports/overview/').data
        self.assertEqual(
            {'assets', 'vehicles', 'equipment', 'documents', 'maintenance'},
            set(overview) - {'generated_at'},
        )
        self.assertIn('summary', self.client.get('/api/v1/reports/maintenance/').data)
        for path in (
            '/api/v1/reports/vehicles/',
            '/api/v1/reports/equipment/',
            '/api/v1/reports/documents/',
            '/api/v1/reports/transfers/',
        ):
            body = self.client.get(path).data
            self.assertEqual(body['count'], len(body['results']))

        self.assertEqual(self.client.get('/api/v1/settings/organization/').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/settings/profile/').status_code, 200)

    def test_admin_can_read_notification_settings_and_lists(self):
        admin = User.objects.create_user(username='api-read-admin', password='admin-pass')
        UserRole.objects.create(user=admin, role='admin')
        self.client.force_authenticate(admin)
        for path in (
            '/api/v1/notifications/schedule/',
            '/api/v1/notifications/recipients/?page_size=1',
            '/api/v1/notifications/deliveries/',
            '/api/v1/settings/notifications/',
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIsInstance(response.data, dict)


@override_settings(SECURE_SSL_REDIRECT=False)
class WorkflowDetailApiContractTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username='workflow-detail-manager', password='manager-pass')
        UserRole.objects.create(user=self.manager, role='manager')
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def test_transfer_and_driver_request_details_are_readable(self):
        equipment = OfficeEquipment.objects.create(name='Detail API Equipment', assigned_user='Previous Owner')
        transfer = EquipmentTransfer.objects.create(
            equipment=equipment,
            transferred_from='Previous Owner',
            transferred_to='Next Owner',
            recorded_by=self.manager,
        )
        transfer_response = self.client.get(f'/api/equipment-transfers/{transfer.pk}/')
        self.assertEqual(transfer_response.status_code, 200)
        self.assertEqual(transfer_response.data['transferred_to'], 'Next Owner')

        driver_request = DriverRequest.objects.create(
            requester_user=self.manager,
            details='Read request detail',
        )
        request_response = self.client.get(f'/api/driver-requests/{driver_request.pk}/')
        self.assertEqual(request_response.status_code, 200)
        self.assertEqual(request_response.data['details'], 'Read request detail')