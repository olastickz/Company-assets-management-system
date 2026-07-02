from datetime import date, timedelta
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
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
    result = send_expiry_alerts()
    
    # If alerts were sent, update the last_sent timestamp
    if result['status'] == 'sent':
        try:
            schedule = EmailSchedule.objects.first()
            if schedule:
                schedule.last_sent = timezone.now()
                schedule.save(update_fields=['last_sent'])
        except EmailSchedule.DoesNotExist:
            pass
    
    return result