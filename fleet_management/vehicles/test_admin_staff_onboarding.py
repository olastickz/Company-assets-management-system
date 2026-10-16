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
            'password': 'Initial!StaffPassword_2026',
            'department': 'ABS',
            'branch': 'LAGOS',
            'is_active': True,
        }
        data.update(overrides)
        return data

    def test_admin_api_creates_staff_login_with_emailed_temporary_password(self):
        api_client = APIClient()
        api_client.force_authenticate(self.admin)
        data = self.staff_data()
        data.pop('password')
        response = api_client.post(
            reverse('api-v1-admin-staff'), data, format='json'
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['account_status'], 'active')
        self.assertTrue(response.data['is_active'])
        staff = StaffMember.objects.get(staff_id='ADMIN-STAFF-001')
        user = User.objects.get(username='ADMIN-STAFF-001')
        self.assertEqual(staff.user_id, user.pk)
        self.assertEqual(user.role.role, 'staff')
        self.assertTrue(user.is_active)
        self.assertTrue(staff.is_active)
        self.assertEqual(len(mail.outbox), 1)
        email_body = mail.outbox[0].body
        temporary_password = email_body.split('Temporary password: ', 1)[1].splitlines()[0]
        self.assertTrue(user.check_password(temporary_password))
        self.assertIn('Username (staff ID): ADMIN-STAFF-001', email_body)
        self.assertIn('change your password immediately', email_body)
        user.refresh_from_db()

    def test_admin_user_api_creates_staff_without_password_and_emails_credentials(self):
        api_client = APIClient()
        api_client.force_authenticate(self.admin)
        response = api_client.post(reverse('api-v1-admin-users'), {
            'username': 'ADMIN-USER-STAFF-001',
            'first_name': 'Nia',
            'last_name': 'Adebayo',
            'email': 'nia@example.test',
            'role': 'staff',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username='ADMIN-USER-STAFF-001')
        email_body = mail.outbox[-1].body
        temporary_password = email_body.split('Temporary password: ', 1)[1].splitlines()[0]
        self.assertTrue(user.check_password(temporary_password))
        self.assertIn('ADMIN-USER-STAFF-001', email_body)
        user.refresh_from_db()

    def test_assigning_staff_role_emails_new_temporary_password(self):
        user = User.objects.create_user(
            username='promoted-user',
            email='promoted@example.test',
            password='Initial!StaffPassword_2026',
        )
        UserRole.objects.create(user=user, role='vehicle_manager')
        api_client = APIClient()
        api_client.force_authenticate(self.admin)

        response = api_client.patch(
            reverse('api-v1-admin-user-detail', args=[user.pk]),
            {'role': 'staff'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        email_body = mail.outbox[-1].body
        temporary_password = email_body.split('Temporary password: ', 1)[1].splitlines()[0]
        self.assertEqual(user.role.role, 'staff')
        self.assertTrue(user.check_password(temporary_password))
        self.assertIn('promoted-user', email_body)

    def test_admin_staff_form_creates_login_with_emailed_temporary_password(self):
        client = Client()
        client.force_login(self.admin)
        data = self.staff_data(staff_id='ADMIN-FORM-001')
        data.pop('password')
        response = client.post(reverse('staff_create'), {
            **data,
        })

        self.assertEqual(response.status_code, 302)
        staff = StaffMember.objects.get(staff_id='ADMIN-FORM-001')
        user = User.objects.get(username='ADMIN-FORM-001')
        self.assertEqual(staff.user_id, user.pk)
        self.assertTrue(user.is_active)
        self.assertTrue(staff.is_active)
        email_body = mail.outbox[-1].body
        temporary_password = email_body.split('Temporary password: ', 1)[1].splitlines()[0]
        self.assertTrue(user.check_password(temporary_password))
        self.assertIn('ADMIN-FORM-001', email_body)

    def test_staff_can_change_password_after_authenticating(self):
        user = User.objects.create_user(
            username='self-service-staff',
            password='Initial!StaffPassword_2026',
        )
        UserRole.objects.create(user=user, role='staff')
        api_client = APIClient()
        api_client.force_authenticate(user)

        response = api_client.post('/api/v1/settings/password/', {
            'current_password': 'Initial!StaffPassword_2026',
            'new_password': 'Updated!StaffPassword_2026',
            'password_confirm': 'Updated!StaffPassword_2026',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password('Updated!StaffPassword_2026'))

    def test_staff_password_change_rejects_wrong_current_password(self):
        user = User.objects.create_user(
            username='password-change-user',
            password='Initial!StaffPassword_2026',
        )
        api_client = APIClient()
        api_client.force_authenticate(user)

        response = api_client.post('/api/v1/settings/password/', {
            'current_password': 'wrong-current-password',
            'new_password': 'Updated!StaffPassword_2026',
            'password_confirm': 'Updated!StaffPassword_2026',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        user.refresh_from_db()
        self.assertTrue(user.check_password('Initial!StaffPassword_2026'))

    def test_staff_can_change_password_from_authenticated_page(self):
        user = User.objects.create_user(
            username='web-password-change-user',
            password='Initial!StaffPassword_2026',
        )
        client = Client()
        client.force_login(user)

        response = client.post(reverse('password_change'), {
            'old_password': 'Initial!StaffPassword_2026',
            'new_password1': 'Updated!StaffPassword_2026',
            'new_password2': 'Updated!StaffPassword_2026',
        })

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.check_password('Updated!StaffPassword_2026'))

    def test_staff_cannot_self_apply(self):
        response = Client().post('/staff/apply/', self.staff_data())

        self.assertEqual(response.status_code, 302)
        self.assertFalse(StaffApplication.objects.exists())