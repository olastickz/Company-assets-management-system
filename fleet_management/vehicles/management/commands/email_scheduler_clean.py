"""
Django management command to check and control the email scheduler
Run with: python manage.py email_scheduler status|trigger|restart
"""

from django.core.management.base import BaseCommand
from vehicles.email_notifications import send_expiry_alerts
from vehicles.apps import scheduler


class Command(BaseCommand):
    help = 'Check and control the email scheduler'

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=['status', 'trigger', 'restart'],
            help='Action to perform'
        )

    def handle(self, *args, **options):
        action = options['action']

        if action == 'status':
            self.show_status()
        elif action == 'trigger':
            self.trigger_email()
        elif action == 'restart':
            self.restart_scheduler()

    def show_status(self):
        """Show current scheduler status"""
        if scheduler and scheduler.running:
            jobs = scheduler.get_jobs()
            self.stdout.write(
                self.style.SUCCESS(f'✅ Scheduler is running with {len(jobs)} job(s)')
            )
            for job in jobs:
                self.stdout.write(f'  • {job.id}: {job.trigger}')
        else:
            self.stdout.write(
                self.style.WARNING('⏸️  Scheduler is not running')
            )

    def trigger_email(self):
        """Manually trigger email sending"""
        self.stdout.write('📧 Triggering email check...')
        result = send_expiry_alerts()

        if result['status'] == 'sent':
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Email sent to {len(result["recipients"])} recipient(s)\n'
                    f'   Vehicles: {result["vehicles_count"]}, Equipment: {result["equipment_count"]}'
                )
            )
        elif result['status'] == 'no_alerts':
            self.stdout.write(
                self.style.WARNING('⚠️  No expiring items found')
            )
        else:
            self.stdout.write(
                self.style.ERROR(f'❌ {result["message"]}')
            )

    def restart_scheduler(self):
        """Restart the scheduler"""
        from vehicles.apps import VehiclesConfig
        config = VehiclesConfig('vehicles', None)

        if scheduler and scheduler.running:
            scheduler.shutdown()
            self.stdout.write('⏹️  Stopped existing scheduler')

        config.setup_scheduler()
        self.stdout.write(
            self.style.SUCCESS('✅ Scheduler restarted')
        )