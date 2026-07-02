"""
Django management command to check and control the email scheduler
Run with: python manage.py email_scheduler status|trigger|restart
"""

from django.core.management.base import BaseCommand
from vehicles.email_notifications import send_expiry_alerts
from vehicles.apps import scheduler


class Command(BaseCommand):
    help = 'Check and control the email scheduler system'

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=['status', 'trigger', 'restart'],
            help='Action to perform: status (show current state), trigger (send emails now), restart (restart scheduler)'
        )

    def handle(self, *args, **options):
        action = options['action']

        if action == 'status':
            self.show_status()
        elif action == 'trigger':
            self.trigger_emails()
        elif action == 'restart':
            self.restart_scheduler()

    def show_status(self):
        """Show current scheduler and email system status"""
        self.stdout.write(self.style.SUCCESS('\n📊 Email Scheduler Status'))
        self.stdout.write('=' * 50)

        # Check scheduler
        if scheduler and scheduler.running:
            self.stdout.write(self.style.SUCCESS('✅ Scheduler: RUNNING'))

            job = scheduler.get_job("daily_expiry_alerts_job")
            if job:
                next_run = job.next_run_time
                self.stdout.write(f'📅 Next run: {next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else "Not scheduled"}')
            else:
                self.stdout.write(self.style.WARNING('⚠️  No scheduled job found'))
        else:
            self.stdout.write(self.style.ERROR('❌ Scheduler: NOT RUNNING'))

        # Check email configuration
        from vehicles.models import EmailSchedule, EmailRecipient

        schedule = EmailSchedule.objects.first()
        if schedule:
            status = "✅ ENABLED" if schedule.is_enabled else "❌ DISABLED"
            self.stdout.write(f'⏰ Schedule: {schedule.schedule_time.strftime("%H:%M")} ({status})')
            self.stdout.write(f'📆 Alert Window: {schedule.alert_days} days')
            self.stdout.write(f'📧 Last Sent: {schedule.last_sent.strftime("%Y-%m-%d %H:%M") if schedule.last_sent else "Never"}')
        else:
            self.stdout.write(self.style.ERROR('❌ No email schedule configured'))

        # Check recipients
        recipients = EmailRecipient.objects.filter(is_active=True)
        self.stdout.write(f'👥 Active Recipients: {len(recipients)}')
        for r in recipients:
            self.stdout.write(f'   - {r.email}')

        # Check expiring items
        from vehicles.email_notifications import get_expiring_vehicles, get_expiring_equipment
        expiring_vehicles = get_expiring_vehicles()
        expiring_equipment = get_expiring_equipment()

        self.stdout.write(f'🚨 Expiring Items: {len(expiring_vehicles) + len(expiring_equipment)} total')
        self.stdout.write(f'   Vehicles: {len(expiring_vehicles)}')
        self.stdout.write(f'   Equipment: {len(expiring_equipment)}')

        self.stdout.write('=' * 50)

    def trigger_emails(self):
        """Manually trigger email sending"""
        self.stdout.write(self.style.SUCCESS('\n🚀 Triggering Email Alerts...'))
        self.stdout.write('=' * 50)

        result = send_expiry_alerts()

        self.stdout.write(f"📊 Status: {result['status'].upper()}")

        if result['status'] == 'sent':
            self.stdout.write(self.style.SUCCESS(f"✅ Email sent to {len(result.get('recipients', []))} recipient(s)"))
            for recipient in result.get('recipients', []):
                self.stdout.write(f"   📧 {recipient}")
        elif result['status'] == 'no_alerts':
            self.stdout.write(self.style.WARNING(f"ℹ️  {result.get('message', 'No alerts to send')}"))
        else:
            self.stdout.write(self.style.ERROR(f"❌ {result.get('message', 'Failed to send email')}"))

        self.stdout.write('=' * 50)

    def restart_scheduler(self):
        """Restart the scheduler with current settings"""
        self.stdout.write(self.style.SUCCESS('\n🔄 Restarting Email Scheduler...'))
        self.stdout.write('=' * 50)

        global scheduler
        if scheduler:
            scheduler.shutdown(wait=True)
            self.stdout.write('🛑 Stopped existing scheduler')

        # Reinitialize scheduler
        from vehicles.apps import VehiclesConfig
        config = VehiclesConfig('vehicles', None)
        config.setup_scheduler()

        self.stdout.write(self.style.SUCCESS('✅ Scheduler restarted'))
        self.show_status()