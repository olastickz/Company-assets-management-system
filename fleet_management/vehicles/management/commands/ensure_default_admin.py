import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Ensure the deployment has a working default admin account.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset-password',
            action='store_true',
            help='Reset managed admin passwords from APP_ADMIN_PASSWORD.',
        )

    def handle(self, *args, **options):
        User = get_user_model()
        username = os.getenv('APP_ADMIN_USERNAME', 'telnet')
        password = os.getenv('APP_ADMIN_PASSWORD')
        if not password:
            raise ValueError('APP_ADMIN_PASSWORD must be configured before creating an admin account.')
        legacy_username = os.getenv('LEGACY_ADMIN_USERNAME', 'Olastickz')
        email = os.getenv('APP_ADMIN_EMAIL', '')
        reset_password = options['reset_password']

        for name in [username, legacy_username]:
            if not name or name == username and legacy_username == username:
                continue

            user, created = User.objects.get_or_create(
                username=name,
                defaults={'email': email, 'is_staff': True, 'is_superuser': True},
            )
            user.email = email or user.email
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            if created or reset_password:
                user.set_password(password)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Ensured admin user '{name}' exists with admin permissions."
                )
            )

        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': email, 'is_staff': True, 'is_superuser': True},
        )
        user.email = email or user.email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        if created or reset_password:
            user.set_password(password)
        user.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Default admin ready: username='{username}', admin permissions ensured."
            )
        )
