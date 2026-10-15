import random

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import StaffApplication, StaffMember, UserRole


def generate_temporary_password():
    characters = [
        get_random_string(1, 'abcdefghijklmnopqrstuvwxyz'),
        get_random_string(1, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'),
        get_random_string(1, '0123456789'),
        get_random_string(1, '!@#$%^&*'),
    ]
    characters.extend(
        get_random_string(20, 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*')
    )
    random.SystemRandom().shuffle(characters)
    return ''.join(characters)


def send_staff_temporary_password(user, password, request, status_url=None):
    login_url = request.build_absolute_uri(reverse('login'))
    body = (
        f'Hello {user.first_name},\n\n'
        'Your Telnet staff account has been approved.\n'
        f'Username (staff ID): {user.username}\n'
        f'Temporary password: {password}\n\n'
        f'Sign in here: {login_url}\n'
        'After logging in, change your password immediately from the Change Password page.\n'
    )
    if status_url:
        body += f'\nYou can also check your application status here: {status_url}\n'

    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        user.set_password(password)
        user.save(update_fields=['password'])
        sent_count = send_mail(
            'Your Telnet staff account login details',
            body,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        if sent_count != 1:
            raise RuntimeError('The temporary password email could not be sent.')
        user.is_active = True
        user.save(update_fields=['is_active'])
        StaffMember.objects.filter(user=user).update(is_active=True)


def send_staff_password_setup_link(user, request, status_url=None):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    setup_url = request.build_absolute_uri(
        reverse('staff_password_setup', kwargs={'uidb64': uid, 'token': token})
    )
    body = (
        f'Hello {user.first_name},\n\n'
        'An administrator created your staff account. Set your password using this secure link:\n'
        f'{setup_url}\n\n'
        f'Your username is your staff ID: {user.username}\n'
        'The link expires automatically after a limited time.'
    )
    if status_url:
        body += f'\n\nYou can also check your application status here: {status_url}'

    sent_count = send_mail(
        'Set up your Telnet staff account',
        body,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )
    if sent_count != 1:
        raise RuntimeError('The password setup email could not be sent.')
    return setup_url


def provision_staff_account(staff, password=None, request=None):
    email = (staff.email or '').strip().lower()
    if not email:
        raise ValidationError({'email': 'A staff email is required to send login details.'})
    if User.objects.filter(username__iexact=staff.staff_id).exists():
        raise ValidationError({'staff_id': 'An account already uses this staff ID.'})
    if User.objects.filter(email__iexact=email).exists():
        raise ValidationError({'email': 'An account already uses this email address.'})
    if StaffMember.objects.filter(email__iexact=email).exclude(pk=staff.pk).exists():
        raise ValidationError({'email': 'This email address is already listed in the staff registry.'})
    if password:
        try:
            validate_password(password, user=User(username=staff.staff_id, email=email))
        except ValidationError as error:
            raise ValidationError({'password': error.messages}) from error
    else:
        password = generate_temporary_password()
    if request is None:
        raise ValueError('A request is required to email the staff login URL.')

    with transaction.atomic():
        staff.email = email
        staff.is_active = False
        staff.save()

        user = User(
            username=staff.staff_id,
            email=email,
            first_name=staff.first_name,
            last_name=staff.last_name,
            is_active=False,
        )
        user.set_password(password)
        user.save()
        UserRole.objects.create(user=user, role='staff', department=staff.department)

        staff.user = user
        staff.save(update_fields=['user', 'email', 'is_active'])
        send_staff_temporary_password(user, password, request)

    return staff


def send_application_notification(application, request):
    status_url = request.build_absolute_uri(
        reverse('staff_application_status', kwargs={'status_token': application.status_token})
    )

    if application.status == 'pending':
        subject = 'Staff application received'
        body = (
            f'Hello {application.first_name},\n\n'
            'Your staff account application has been received and is awaiting review. '
            f'You can check its status using this private link: {status_url}\n\n'
            'You will receive another email when a decision is made.'
        )
    elif application.status == 'declined':
        subject = 'Update on your staff application'
        body = (
            f'Hello {application.first_name},\n\n'
            'Your staff account application was not approved. '
            f'You can view its status here: {status_url}\n\n'
            'Please contact your administrator if you need more information.'
        )
    elif application.status == 'approved' and application.account_id:
        password = generate_temporary_password()
        return send_staff_temporary_password(application.account, password, request, status_url)
    else:
        raise ValueError('This application is not in an emailable state.')

    return send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [application.email], fail_silently=False)


def review_staff_application(application, decision, reviewer, request):
    if decision not in ('approved', 'declined'):
        raise ValueError('Unsupported application decision.')

    with transaction.atomic():
        application = StaffApplication.objects.select_for_update().get(pk=application.pk)
        if application.status != 'pending':
            raise ValueError('Only pending applications can be reviewed.')

        if decision == 'approved':
            if User.objects.filter(username__iexact=application.staff_id).exists():
                raise ValueError('The staff ID is already used by an account.')
            if User.objects.filter(email__iexact=application.email).exists():
                raise ValueError('The email address is already used by an account.')
            if StaffMember.objects.filter(staff_id__iexact=application.staff_id).exists():
                raise ValueError('The staff ID already exists in the staff registry.')
            if StaffMember.objects.filter(email__iexact=application.email).exists():
                raise ValueError('The email already exists in the staff registry.')

            user = User(
                username=application.staff_id,
                email=application.email,
                first_name=application.first_name,
                last_name=application.last_name,
                is_active=False,
            )
            user.set_unusable_password()
            user.save()
            UserRole.objects.create(user=user, role='staff', department=application.department)
            StaffMember.objects.create(
                user=user,
                staff_id=application.staff_id,
                first_name=application.first_name,
                last_name=application.last_name,
                email=application.email,
                department=application.department,
                branch=application.branch,
                is_active=False,
            )
            application.account = user

        application.status = decision
        application.reviewed_by = reviewer
        application.reviewed_at = timezone.now()
        application.save(update_fields=['status', 'account', 'reviewed_by', 'reviewed_at'])

    send_application_notification(application, request)
    return application