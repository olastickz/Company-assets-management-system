"""
Django management command to send expiry alert emails.
Run with: python manage.py send_expiry_alerts
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from vehicles.email_notifications import send_expiry_alerts


class Command(BaseCommand):
    help = 'Send expiry alert emails for vehicles and office equipment expiring within 30 days'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n✨ Starting expiry alert check...'))
        
        result = send_expiry_alerts()
        
        self.stdout.write(f'\n📊 Results:')
        self.stdout.write(f'   Status: {result["status"].upper()}')
        self.stdout.write(f'   Vehicles: {result.get("vehicles_count", 0)} expiring')
        self.stdout.write(f'   Equipment: {result.get("equipment_count", 0)} expiring')
        
        if result['status'] == 'sent':
            recipients = result.get('recipients', [])
            self.stdout.write(self.style.SUCCESS(f'✓ Email sent to {len(recipients)} recipient(s):'))
            for recipient in recipients:
                self.stdout.write(f'   - {recipient}')
        elif result['status'] == 'no_alerts':
            self.stdout.write(self.style.WARNING(f'ⓘ {result["message"]}'))
        else:
            self.stdout.write(self.style.ERROR(f'✗ {result["message"]}'))
            if 'error' in result:
                self.stdout.write(f'   Error: {result["error"]}')
        
        self.stdout.write(self.style.SUCCESS('\n✨ Expiry alert check completed!\n'))
