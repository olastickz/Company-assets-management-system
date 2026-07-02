"""
Email notification system for upcoming expiries in vehicles and office equipment.
Sends alerts for items expiring within 30 days or already expired.
"""

from django.core.mail import send_mail
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import Vehicle, OfficeEquipment, EmailRecipient, EmailSchedule, EmailDeliveryLog, CompanyDocument

def get_expiring_vehicles(alert_days=30):
    """
    Get all vehicles with upcoming or already expired items.
    Returns a dictionary with expiry status for each vehicle.
    """
    today = timezone.now().date()
    expiring_items = []
    
    vehicles = Vehicle.objects.all()
    
    expiry_fields = [
        ('insurance_expiry', 'Insurance'),
        ('roadworthy_expiry', 'Roadworthy Certificate'),
        ('license_expiry', 'License'),
        ('hackney_permit', 'Hackney Permit'),
    ]
    
    for vehicle in vehicles:
        for field_name, field_label in expiry_fields:
            expiry_date = getattr(vehicle, field_name, None)
            
            if not expiry_date:
                continue
            
            days_until_expiry = (expiry_date - today).days
            
            # Alert for items expiring within the configured alert window (but not already expired)
            if 0 <= days_until_expiry <= alert_days:
                status = 'expiring'
                expiring_items.append({
                    'vehicle_name': vehicle.name,
                    'license_plate': vehicle.license_plate,
                    'type': 'vehicle',
                    'item_type': field_label,
                    'expiry_date': expiry_date,
                    'days_until_expiry': days_until_expiry,
                    'status': status,
                    'url': f'/vehicle/{vehicle.id}/'
                })
            # Mark expired items as pending certification
            elif days_until_expiry < 0 and vehicle.status == 'active':
                vehicle.status = 'pending_certification'
                vehicle.save(update_fields=['status'])
    
    return expiring_items


def get_expiring_equipment(alert_days=30):
    """
    Get all office equipment with upcoming or already expired warranties.
    Returns a dictionary with expiry status for each equipment.
    """
    today = timezone.now().date()
    expiring_items = []
    
    equipment_list = OfficeEquipment.objects.all()
    
    for equipment in equipment_list:
        if not equipment.warranty_expiry:
            continue
        
        days_until_expiry = (equipment.warranty_expiry - today).days
        
        # Alert for items expiring within the configured alert window (but not already expired)
        if 0 <= days_until_expiry <= alert_days:
            status = 'expiring'
            expiring_items.append({
                'equipment_name': equipment.name,
                'equipment_type': equipment.get_equipment_type_display(),
                'subsidiary': equipment.subsidiary,
                'type': 'equipment',
                'item_type': 'Warranty',
                'expiry_date': equipment.warranty_expiry,
                'days_until_expiry': days_until_expiry,
                'status': status,
                'url': f'/equipment/{equipment.id}/'
            })
        # Mark expired items as pending certification
        elif days_until_expiry < 0 and equipment.status == 'active':
            equipment.status = 'pending_certification'
            equipment.save(update_fields=['status'])
    
    return expiring_items


def get_expiring_documents():
    """Get all company documents that are expired or within their notification window."""
    today = timezone.now().date()
    expiring_items = []
    documents = CompanyDocument.objects.all()

    for document in documents:
        if not document.expiry_date:
            continue

        days_until_expiry = (document.expiry_date - today).days
        status = document.get_status()
        notify_window = document.notify_days_before if document.notify_days_before is not None else 30

        if days_until_expiry < 0 or 0 <= days_until_expiry <= notify_window:
            expiring_items.append({
                'document_name': document.name,
                'document_type': document.get_document_type_display(),
                'document_number': document.document_number,
                'expiry_date': document.expiry_date,
                'days_until_expiry': days_until_expiry,
                'status': status,
                'notify_days_before': notify_window,
                'url': f'/documents/{document.id}/'
            })

    return expiring_items


def _log_email_delivery(recipient_email, subject, status, message='', error_message=None):
    recipient = EmailRecipient.objects.filter(email=recipient_email).first()
    EmailDeliveryLog.objects.create(
        recipient=recipient,
        recipient_email=recipient_email,
        subject=subject,
        status=status,
        message=message,
        error_message=error_message,
        sent_at=timezone.now() if status == 'sent' else None,
    )


def send_expiry_alerts():
    """
    Send expiry alert emails for vehicles and office equipment.
    Combines all expiring items into a single comprehensive email.
    """
    # Get alert days from EmailSchedule (default to 30 if not configured)
    try:
        schedule = EmailSchedule.objects.first()
        alert_days = schedule.alert_days if schedule else 30
    except Exception:
        alert_days = 30

    expiring_vehicles = get_expiring_vehicles(alert_days)
    expiring_equipment = get_expiring_equipment(alert_days)
    expiring_documents = get_expiring_documents()

    # If there are no expiring items, don't send email
    if not expiring_vehicles and not expiring_equipment and not expiring_documents:
        return {
            'status': 'no_alerts',
            'message': f'No items expiring within {alert_days} days',
            'vehicles_count': 0,
            'equipment_count': 0,
            'documents_count': 0
        }

    # Get active recipients from database
    active_recipients = EmailRecipient.objects.filter(is_active=True).values_list('email', flat=True)
    recipient_emails = list(active_recipients)

    if not recipient_emails:
        return {
            'status': 'no_recipients',
            'message': 'No active email recipients configured',
            'vehicles_count': len(expiring_vehicles),
            'equipment_count': len(expiring_equipment)
        }

    # Prepare email context
    now = timezone.now()
    total_count = len(expiring_vehicles) + len(expiring_equipment) + len(expiring_documents)
    context = {
        'expiring_vehicles': expiring_vehicles,
        'expiring_equipment': expiring_equipment,
        'expiring_documents': expiring_documents,
        'total_alerts': total_count,
        'alert_days': alert_days,
        'today': now,
    }

    # Render HTML email template
    html_message = render_to_string('email_expiry_alert.html', context)
    plain_message = strip_tags(html_message)

    sender_email = settings.ALERT_EMAIL_FROM
    subject = f'🚨 Assets Management Alert: {total_count} items expiring or expired'

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=sender_email,
            recipient_list=recipient_emails,
            html_message=html_message,
            fail_silently=False,
        )

        # Batch create delivery logs to reduce database lock time
        logs_to_create = []
        for recipient_email in recipient_emails:
            recipient = EmailRecipient.objects.filter(email=recipient_email).first()
            logs_to_create.append(
                EmailDeliveryLog(
                    recipient=recipient,
                    recipient_email=recipient_email,
                    subject=subject,
                    status='sent',
                    message=f'Expiry alert sent to {recipient_email}',
                    sent_at=timezone.now(),
                )
            )
        EmailDeliveryLog.objects.bulk_create(logs_to_create, batch_size=10)

        return {
            'status': 'sent',
            'message': f'Email sent to {len(recipient_emails)} recipient(s)',
            'vehicles_count': len(expiring_vehicles),
            'equipment_count': len(expiring_equipment),
            'documents_count': len(expiring_documents),
            'recipients': recipient_emails
        }

    except Exception as e:
        # Batch create failed delivery logs
        logs_to_create = []
        for recipient_email in recipient_emails:
            recipient = EmailRecipient.objects.filter(email=recipient_email).first()
            logs_to_create.append(
                EmailDeliveryLog(
                    recipient=recipient,
                    recipient_email=recipient_email,
                    subject=subject,
                    status='failed',
                    message='Expiry alert failed to send',
                    error_message=str(e),
                )
            )
        try:
            EmailDeliveryLog.objects.bulk_create(logs_to_create, batch_size=10)
        except Exception as log_err:
            print(f"Failed to log delivery error: {log_err}")

        return {
            'status': 'failed',
            'message': f'Failed to send email: {str(e)}',
            'vehicles_count': len(expiring_vehicles),
            'equipment_count': len(expiring_equipment),
            'error': str(e)
        }


def send_vehicle_expiry_email(vehicle_id):
    """
    Send expiry alert for a specific vehicle.
    Useful for manual triggers when vehicle details are updated.
    """
    try:
        vehicle = Vehicle.objects.get(id=vehicle_id)
        today = timezone.now().date()
        
        # Get alert days from EmailSchedule (default to 30 if not configured)
        try:
            schedule = EmailSchedule.objects.first()
            alert_days = schedule.alert_days if schedule else 30
        except EmailSchedule.DoesNotExist:
            alert_days = 30
        
        expiry_fields = [
            ('insurance_expiry', 'Insurance'),
            ('roadworthy_expiry', 'Roadworthy Certificate'),
            ('license_expiry', 'License'),
            ('hackney_permit', 'Hackney Permit'),
        ]
        
        alerts = []
        for field_name, field_label in expiry_fields:
            expiry_date = getattr(vehicle, field_name, None)
            if expiry_date and (expiry_date - today).days <= alert_days:
                alerts.append({
                    'item_type': field_label,
                    'expiry_date': expiry_date,
                    'days_until_expiry': (expiry_date - today).days
                })
        
        if not alerts:
            return {'status': 'no_alerts', 'message': f'{vehicle.name} has no items expiring within {alert_days} days'}
        
        # Get active recipients from database
        active_recipients = EmailRecipient.objects.filter(is_active=True).values_list('email', flat=True)
        recipient_emails = list(active_recipients)
        
        if not recipient_emails:
            return {'status': 'no_recipients', 'message': 'No active email recipients configured'}
        
        context = {
            'vehicle': vehicle,
            'alerts': alerts,
            'today': today,
        }
        
        html_message = render_to_string('email_vehicle_expiry.html', context)
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=f'⚠️ Vehicle Expiry Alert: {vehicle.name} ({vehicle.license_plate})',
            message=plain_message,
            from_email=settings.ALERT_EMAIL_FROM,
            recipient_list=recipient_emails,
            html_message=html_message,
            fail_silently=False,
        )
        for recipient_email in recipient_emails:
            _log_email_delivery(
                recipient_email=recipient_email,
                subject=f'⚠️ Vehicle Expiry Alert: {vehicle.name} ({vehicle.license_plate})',
                status='sent',
                message=f'Vehicle expiry alert sent for {vehicle.name}',
            )

        return {
            'status': 'sent',
            'message': f'Alert email sent for {vehicle.name}',
            'alerts_count': len(alerts)
        }
    
    except Vehicle.DoesNotExist:
        return {'status': 'error', 'message': f'Vehicle with ID {vehicle_id} not found'}
    except Exception as e:
        return {'status': 'error', 'message': f'Failed to send email: {str(e)}'}


def send_equipment_expiry_email(equipment_id):
    """
    Send expiry alert for a specific equipment item.
    Useful for manual triggers when equipment details are updated.
    """
    try:
        equipment = OfficeEquipment.objects.get(id=equipment_id)
        today = timezone.now().date()
        
        # Get alert days from EmailSchedule (default to 30 if not configured)
        try:
            schedule = EmailSchedule.objects.first()
            alert_days = schedule.alert_days if schedule else 30
        except EmailSchedule.DoesNotExist:
            alert_days = 30
        
        if not equipment.warranty_expiry:
            return {'status': 'no_alerts', 'message': f'{equipment.name} has no warranty expiry date'}
        
        days_until_expiry = (equipment.warranty_expiry - today).days
        if days_until_expiry > alert_days:
            return {'status': 'no_alerts', 'message': f'{equipment.name} warranty expires in {days_until_expiry} days (beyond {alert_days}-day window)'}
        
        # Get active recipients from database
        active_recipients = EmailRecipient.objects.filter(is_active=True).values_list('email', flat=True)
        recipient_emails = list(active_recipients)
        
        if not recipient_emails:
            return {'status': 'no_recipients', 'message': 'No active email recipients configured'}
        
        context = {
            'equipment': equipment,
            'days_until_expiry': days_until_expiry,
            'today': today,
        }
        
        html_message = render_to_string('email_equipment_expiry.html', context)
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=f'⚠️ Equipment Expiry Alert: {equipment.name} - Warranty Expiring',
            message=plain_message,
            from_email=settings.ALERT_EMAIL_FROM,
            recipient_list=recipient_emails,
            html_message=html_message,
            fail_silently=False,
        )
        for recipient_email in recipient_emails:
            _log_email_delivery(
                recipient_email=recipient_email,
                subject=f'⚠️ Equipment Expiry Alert: {equipment.name} - Warranty Expiring',
                status='sent',
                message=f'Equipment expiry alert sent for {equipment.name}',
            )

        return {
            'status': 'sent',
            'message': f'Alert email sent for {equipment.name}',
            'expiry_date': equipment.warranty_expiry,
            'days_until_expiry': days_until_expiry
        }
    
    except OfficeEquipment.DoesNotExist:
        return {'status': 'error', 'message': f'Equipment with ID {equipment_id} not found'}
    except Exception as e:
        return {'status': 'error', 'message': f'Failed to send email: {str(e)}'}
