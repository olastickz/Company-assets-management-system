"""Run the email scheduler as a long-lived VPS process."""

from apscheduler.schedulers.blocking import BlockingScheduler
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from vehicles.models import EmailSchedule
from vehicles.scheduler import send_scheduled_expiry_alerts


class Command(BaseCommand):
    help = 'Run the expiry email scheduler in the foreground'

    def handle(self, *args, **options):
        scheduler = BlockingScheduler(timezone=timezone.get_default_timezone())
        scheduler.add_job(
            self.run_if_due,
            trigger='interval',
            seconds=30,
            id='email_expiry_scheduler_tick',
            max_instances=1,
            coalesce=True,
        )

        self.stdout.write(self.style.SUCCESS('Email scheduler started'))
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown(wait=False)
            self.stdout.write('Email scheduler stopped')

    def run_if_due(self):
        close_old_connections()
        schedule = EmailSchedule.objects.first()
        if not schedule or not schedule.is_enabled:
            return

        now = timezone.localtime()
        if (now.hour, now.minute) != (
            schedule.schedule_time.hour,
            schedule.schedule_time.minute,
        ):
            return

        if schedule.last_sent and timezone.localtime(schedule.last_sent).date() == now.date():
            return

        result = send_scheduled_expiry_alerts()
        self.stdout.write(f'Email scheduler result: {result["status"]}')