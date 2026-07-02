"""
Django management command to setup the email schedule in APScheduler.
Run with: python manage.py setup_email_scheduler
"""

from django.core.management.base import BaseCommand
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.jobstores import DjangoJobStore
from apscheduler.schedulers.base import ScheduleAlreadyRunningError
from django.utils import timezone
import logging
from vehicles.models import EmailSchedule
from vehicles.scheduler import send_scheduled_expiry_alerts

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Setup the scheduled email alerts for expiring items'

    def handle(self, *args, **options):
        scheduler = BackgroundScheduler()
        scheduler.add_jobstore(DjangoJobStore(), "default")
        
        try:
            # Get the email schedule configuration
            schedule = EmailSchedule.objects.first()
            
            if not schedule:
                self.stdout.write(self.style.WARNING('⚠️ No EmailSchedule configuration found!'))
                self.stdout.write(self.style.WARNING('Please add an EmailSchedule record in Django admin first.'))
                return
            
            if not schedule.is_enabled:
                self.stdout.write(self.style.WARNING('⚠️ Email schedule is disabled in configuration'))
                return
            
            # Schedule the job
            scheduler.add_job(
                send_scheduled_expiry_alerts,
                trigger=CronTrigger(
                    hour=schedule.schedule_time.hour,
                    minute=schedule.schedule_time.minute,
                    timezone=timezone.get_default_timezone()
                ),
                id='daily_expiry_alerts_job',
                name='Send Expiry Alert Emails',
                misfire_grace_time=15 * 60,  # 15 minute grace period
                replace_existing=True,
            )
            
            scheduler.start()
            
            self.stdout.write(self.style.SUCCESS('✅ Scheduler Started Successfully!'))
            self.stdout.write(f'⏰ Daily emails scheduled at: {schedule.schedule_time.strftime("%H:%M")}')
            self.stdout.write('📧 Emails will be sent for any expiring items')
            
        except ScheduleAlreadyRunningError:
            self.stdout.write(self.style.WARNING('⚠️ Scheduler already running'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error setting up scheduler: {str(e)}'))
            logger.error(f'Error setting up scheduler: {str(e)}')
