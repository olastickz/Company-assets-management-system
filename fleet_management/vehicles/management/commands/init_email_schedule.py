"""
Django management command to initialize the email schedule.
Run with: python manage.py init_email_schedule
"""

from django.core.management.base import BaseCommand
from vehicles.models import EmailSchedule
from datetime import time


class Command(BaseCommand):
    help = 'Initialize the email schedule if it does not exist'

    def add_arguments(self, parser):
        parser.add_argument(
            '--time',
            type=str,
            default='09:00',
            help='Schedule time in HH:MM format (default: 09:00)'
        )

    def handle(self, *args, **options):
        try:
            schedule, created = EmailSchedule.objects.get_or_create(
                pk=1,
                defaults={
                    'schedule_time': time(9, 0),
                    'is_enabled': True,
                }
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS('✅ Email schedule initialized successfully!'))
                self.stdout.write(f'⏰ Default schedule time: 09:00 (9:00 AM)')
                self.stdout.write('📧 Go to Django Admin to modify the schedule time')
            else:
                self.stdout.write(self.style.WARNING('⚠️ Email schedule already exists'))
                self.stdout.write(f'⏰ Current schedule time: {schedule.schedule_time.strftime("%H:%M")}')
                self.stdout.write(f'📧 Status: {"Enabled ✅" if schedule.is_enabled else "Disabled ❌"}')
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error initializing schedule: {str(e)}'))
