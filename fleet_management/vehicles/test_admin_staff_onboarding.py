import re

from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .models import StaffApplication, StaffMember, UserRole


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', DEFAULT_FROM_EMAIL='noreply@example.test', SECURE_SSL_REDIRECT=False)
class AdminStaffOnboardingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='staff-onboarding-admin',
            email='admin@example.test',
            password='Admin!Password_2026',
        )
        UserRole.objects.create(user=self.admin, role='admin')

    def staff_data(self, **overrides):
        data = {
            'staff_id': 'ADMIN-STAFF-001',
            'first_name': 'Mina',
            'last_name': 'Okafor',
            'email': 'mina.okafor@example.test',
            'department': 'ABS',
            'branch': 'LAGOS',
            'is_active': True,
        }
        data.update(overrides)
        return data

    def assert_password_setup_link_activates_staff(self, staff, user):
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertFalse(staff.is_active)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [staff.email])
        self.assertIn('username is your staff ID', mail.outbox[0].body)
        setup_url = re.search(r'http://testserver/reset/[^\s]+', mail.outbox[0].body).group(0)
        setup_path = setup_url.replace('http://testserver', '')

        client = Client()
        setup_response = client.get(setup_path, follow=True)
        self.assertEqual(setup_response.status_code, 200)
        confirm_path = setup_response.request['PATH_INFO']
        password = 'NewStaff!Password_2026'
        response = client.post(confirm_path, {
            'new_password1': password,
            'new_password2': password,
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        staff.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(staff.is_active)
        self.assertTrue(client.login(username=staff.staff_id, password=password))

    def test_admin_api_creates_inactive_staff_login_and_sends_setup_link(self):
        api_client = APIClient()
        api_client.force_authenticate(self.admin)
        response = api_client.post(
            reverse('api-v1-admin-staff'), self.staff_data(), format='json'
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['setup_email_sent'])
        self.assertEqual(response.data['account_status'], 'pending_password')
        staff = StaffMember.objects.get(staff_id='ADMIN-STAFF-001')
        user = User.objects.get(username='ADMIN-STAFF-001')
        self.assertEqual(staff.user_id, user.pk)
        self.assertEqual(user.role.role, 'staff')
        self.assert_password_setup_link_activates_staff(staff, user)

    def test_admin_staff_form_creates_login_and_sends_setup_link(self):
        client = Client()
        client.force_login(self.admin)
        response = client.post(reverse('staff_create'), self.staff_data(staff_id='ADMIN-FORM-001'))

        self.assertEqual(response.status_code, 302)
        staff = StaffMember.objects.get(staff_id='ADMIN-FORM-001')
        user = User.objects.get(username='ADMIN-FORM-001')
        self.assertEqual(staff.user_id, user.pk)
        self.assert_password_setup_link_activates_staff(staff, user)

    def test_staff_cannot_self_apply(self):
        response = Client().post('/staff/apply/', self.staff_data())

        self.assertEqual(response.status_code, 302)
        self.assertFalse(StaffApplication.objects.exists())