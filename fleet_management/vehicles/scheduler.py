from datetime import date, timedelta
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.db import OperationalError
from .models import Vehicle, OfficeEquipment, EmailSchedule
from .email_notifications import send_expiry_alerts


def check_vehicle_expiry():
    """Legacy function - now uses send_expiry_alerts for comprehensive check"""
    result = send_expiry_alerts()
    return result


def send_scheduled_expiry_alerts():
    """
    Scheduled task to send expiry alerts daily.
    Call this from APScheduler to run at regular intervals.
    """
    import time
    
    print("🔔 SCHEDULER TRIGGERED: Checking for expiring items...")

    # Retry logic for database locks (up to 3 attempts)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Check if EmailSchedule exists and is enabled
            try:
                schedule = EmailSchedule.objects.first()
                if not schedule:
                    print("❌ No EmailSchedule found! Create one in Django Admin.")
                    return {'status': 'no_schedule', 'message': 'No EmailSchedule configured'}

                if not schedule.is_enabled:
                    print("⏸️  EmailSchedule is disabled.")
                    return {'status': 'disabled', 'message': 'EmailSchedule is disabled'}

                print(f"✅ Schedule found: {schedule.schedule_time}, Alert days: {schedule.alert_days}")

            except Exception as e:
                print(f"❌ Error checking EmailSchedule: {e}")
                return {'status': 'error', 'message': f'Error checking schedule: {e}'}

            result = send_expiry_alerts()

            # If alerts were sent, update the last_sent timestamp
            if result['status'] == 'sent':
                try:
                    schedule.last_sent = timezone.now()
                    schedule.save(update_fields=['last_sent'])
                    print(f"✅ Last sent timestamp updated to {schedule.last_sent}")
                except Exception as e:
                    print(f"❌ Error updating last_sent: {e}")

            print(f"📧 Result: {result}")
            return result
            
        except OperationalError as db_err:
            if "database is locked" in str(db_err):
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # exponential backoff: 1, 2, 4 seconds
                    print(f"⚠️  Database locked (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ Database still locked after {max_retries} attempts")
                    return {'status': 'error', 'message': 'Database locked - could not complete email send'}
            else:
                print(f"❌ Database error: {db_err}")
                return {'status': 'error', 'message': f'Database error: {db_err}'}
    return result