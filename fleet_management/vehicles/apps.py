import sys

from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate, post_save
from django.utils import timezone

# Global scheduler instance
scheduler = None

class VehiclesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vehicles'
    verbose_name = 'Assets'

    def ready(self):
        from .models import EmailSchedule

        if 'test' in sys.argv:
            # Avoid scheduler startup during test runs to prevent SQLite locking.
            return

        # Make sure the legacy `vehicles.vehicle` content type and permissions exist
        # for old fixture payloads that still reference `Vehicle` by its historical model name.
        post_migrate.connect(self.ensure_legacy_vehicle_permissions, sender=self)

        # Connect the scheduler setup to run after database migrations
        if 'runserver' in sys.argv:
            post_migrate.connect(self.setup_scheduler, sender=self)

        # Connect schedule updates when an EmailSchedule is saved
        post_save.connect(self.update_scheduler, sender=EmailSchedule)

        # Start the scheduler when Django is running as the development server.
        if 'runserver' in sys.argv:
            self.setup_scheduler()

    def ensure_legacy_vehicle_permissions(self, **kwargs):
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        vehicle_content_type, _ = ContentType.objects.get_or_create(
            app_label='vehicles',
            model='vehicle',
        )

        legacy_permissions = {
            'add_vehicle': 'Can add vehicle',
            'change_vehicle': 'Can change vehicle',
            'delete_vehicle': 'Can delete vehicle',
            'view_vehicle': 'Can view vehicle',
        }

        for codename, name in legacy_permissions.items():
            Permission.objects.get_or_create(
                content_type=vehicle_content_type,
                codename=codename,
                defaults={'name': name},
            )

    def setup_scheduler(self, **kwargs):
        global scheduler
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from django_apscheduler.jobstores import DjangoJobStore
        from .scheduler import send_scheduled_expiry_alerts

        if scheduler is None:
            scheduler = BackgroundScheduler()
            scheduler.add_jobstore(DjangoJobStore(), "default")

        # Remove existing current or legacy jobs if they still exist in the database
        legacy_job_ids = [
            "check_vehicle_expiry_job",
            "daily_vehicle_expiry_job",
            "send_expiry_alerts_job",
            "daily_expiry_alerts_job",
        ]
        for job_id in legacy_job_ids:
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
                print(f"🧹 Removed legacy scheduler job: {job_id}")

        try:
            # Try to get the schedule time from EmailSchedule
            from .models import EmailSchedule
            schedule = EmailSchedule.objects.first()

            if schedule and schedule.is_enabled:
                # Use the configured time
                hour = schedule.schedule_time.hour
                minute = schedule.schedule_time.minute
                print(f"Scheduler configured for {hour:02d}:{minute:02d}")
            else:
                # Default to 10:00 AM if not configured
                hour = 10
                minute = 0
                print("Scheduler using default time 10:00")
        except Exception as e:
            # Fallback to 10:00 AM if database not ready
            hour = 10
            minute = 0
            print(f"Scheduler fallback to 10:00 due to: {e}")

        # ⏰ Run every day at the configured time in the Django timezone
        scheduler.add_job(
            send_scheduled_expiry_alerts,
            trigger=CronTrigger(
                hour=hour,
                minute=minute,
                timezone=timezone.get_default_timezone()
            ),
            id="daily_expiry_alerts_job",
            replace_existing=True,
            misfire_grace_time=15 * 60,
            coalesce=True,
        )

        if not scheduler.running:
            scheduler.start()
            print("🚀 Scheduler started!")

    def update_scheduler(self, sender, instance, **kwargs):
        """Update scheduler when EmailSchedule is saved"""
        global scheduler
        if not scheduler:
            self.setup_scheduler()
            return

        if scheduler.get_job("daily_expiry_alerts_job"):
            scheduler.remove_job("daily_expiry_alerts_job")

        if not instance.is_enabled:
            print("⏸️  Email scheduler disabled; job removed")
            return

        # Add updated job
        from apscheduler.triggers.cron import CronTrigger
        from .scheduler import send_scheduled_expiry_alerts

        scheduler.add_job(
            send_scheduled_expiry_alerts,
            trigger=CronTrigger(
                hour=instance.schedule_time.hour,
                minute=instance.schedule_time.minute,
                timezone=timezone.get_default_timezone()
            ),
            id="daily_expiry_alerts_job",
            replace_existing=True,
            misfire_grace_time=15 * 60,
            coalesce=True,
        )
        print(f"🔄 Scheduler updated to {instance.schedule_time.strftime('%H:%M')}")