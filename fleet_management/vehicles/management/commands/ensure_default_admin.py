import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Ensure the deployment has a working default admin account.'

    def handle(self, *args, **options):
        User = get_user_model()
        username = os.getenv('APP_ADMIN_USERNAME', 'telnet')
        password = os.getenv('APP_ADMIN_PASSWORD', 'Olastickz2630')
        legacy_username = os.getenv('LEGACY_ADMIN_USERNAME', 'Olastickz')
        email = os.getenv('APP_ADMIN_EMAIL', '')

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
            user.set_password(password)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Ensured admin user '{name}' exists with a valid password."
                )
            )

        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': email, 'is_staff': True, 'is_superuser': True},
        )
        user.email = email or user.email
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Default admin ready: username='{username}', password is set from APP_ADMIN_PASSWORD or fallback."
            )
        )
