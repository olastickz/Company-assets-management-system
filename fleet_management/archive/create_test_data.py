from django.core.management.base import BaseCommand
from vehicles.models import Vehicle, OfficeEquipment, EmailRecipient, EmailSchedule
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = 'Create sample test data for email alerts testing'

    def handle(self, *args, **options):
        self.stdout.write('🧪 Creating test data for email alerts...')

        # Create EmailSchedule if it doesn't exist
        schedule, created = EmailSchedule.objects.get_or_create(
            defaults={
                'schedule_time': timezone.now().time(),
                'alert_days': 15,
                'is_enabled': True
            }
        )
        if created:
            self.stdout.write('✅ Created EmailSchedule')
        else:
            self.stdout.write('ℹ️  EmailSchedule already exists')

        # Create test email recipient
        recipient, created = EmailRecipient.objects.get_or_create(
            email='test@example.com',
            defaults={
                'full_name': 'Test User',
                'is_active': True
            }
        )
        if created:
            self.stdout.write('✅ Created test email recipient')
        else:
            self.stdout.write('ℹ️  Test email recipient already exists')

        # Create test vehicle with expiring items
        today = timezone.now().date()
        vehicle, created = Vehicle.objects.get_or_create(
            license_plate='TEST-001',
            defaults={
                'name': 'Test Vehicle',
                'vehicle_type': 'car',
                'insurance_expiry': today + timedelta(days=5),  # Expires in 5 days
                'roadworthy_expiry': today + timedelta(days=10),  # Expires in 10 days
            }
        )
        if created:
            self.stdout.write('✅ Created test vehicle with expiring insurance and roadworthy')
        else:
            self.stdout.write('ℹ️  Test vehicle already exists')

        # Create test equipment with expiring warranty
        equipment, created = OfficeEquipment.objects.get_or_create(
            name='Test Laptop',
            defaults={
                'equipment_type': 'computer',
                'subsidiary': 'ITECO',
                'warranty_expiry': today + timedelta(days=7),  # Expires in 7 days
                'cost': 1500.00,
                'status': 'active'
            }
        )
        if created:
            self.stdout.write('✅ Created test equipment with expiring warranty')
        else:
            self.stdout.write('ℹ️  Test equipment already exists')

        self.stdout.write(
            self.style.SUCCESS(
                '\n🎉 Test data created! You can now test the email system.\n'
                'Run: python manage.py test_email\n'
                'Or wait for the scheduled time to trigger automatically.'
            )
        )