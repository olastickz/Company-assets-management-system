import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'fleet_management'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'asset_management.settings')

import django

django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from vehicles.models import EmailDeliveryLog, EmailRecipient, EmailSchedule, UserRole


OUTPUT = ROOT / 'postman'
BASE_URL = 'http://127.0.0.1:8000'


def response_body(response):
    try:
        return response.json()
    except ValueError:
        return response.content.decode('utf-8')


def request_definition(method, path, body=None):
    request = {
        'method': method,
        'header': [{'key': 'Authorization', 'value': 'Token {{token}}'}],
        'url': '{{base_url}}' + path,
    }
    if body is not None:
        request['header'].append({'key': 'Content-Type', 'value': 'application/json'})
        request['body'] = {
            'mode': 'raw',
            'raw': json.dumps(body),
            'options': {'raw': {'language': 'json'}},
        }
    return request


def execute(client, name, method, path, body=None):
    response = getattr(client, method.lower())(path, body, format='json') if body is not None else getattr(client, method.lower())(path)
    example = {
        'name': f'{response.status_code} {response.reason_phrase} - {name}',
        'originalRequest': request_definition(method, path, body),
        'status': response.reason_phrase,
        'code': response.status_code,
        '_postman_previewlanguage': 'json' if response.content else None,
        'header': [],
        'cookie': [],
        'body': json.dumps(response_body(response), default=str) if response.content else '',
    }
    return {
        'name': name,
        'request': request_definition(method, path, body),
        'response': [example],
    }, response.status_code


def write_collection(name, description, requests):
    collection = {
        'info': {
            'name': name,
            'description': description,
            'schema': 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
        },
        'variable': [
            {'key': 'base_url', 'value': BASE_URL},
            {'key': 'token', 'value': ''},
            {'key': 'delivery_id', 'value': '1'},
        ],
        'item': requests,
    }
    OUTPUT.mkdir(exist_ok=True)
    path = OUTPUT / f'{name.lower().replace(" ", "_")}.postman_collection.json'
    path.write_text(json.dumps(collection, indent=2, default=str) + '\n', encoding='utf-8')
    return path


def main():
    User = get_user_model()
    suffix = uuid.uuid4().hex[:8]
    manager = User.objects.create_user(username=f'postman-manager-{suffix}')
    admin = User.objects.create_user(username=f'postman-admin-{suffix}', email=f'postman-{suffix}@example.com')
    UserRole.objects.create(user=manager, role='manager')
    UserRole.objects.create(user=admin, role='admin')
    recipient = EmailRecipient.objects.create(email=f'postman-{suffix}@example.com', created_by=admin)
    delivery = EmailDeliveryLog.objects.create(
        recipient=recipient,
        recipient_email=recipient.email,
        subject='Postman API test',
        status='failed',
        error_message='Test failure',
    )

    schedule = EmailSchedule.objects.first()
    original_schedule = None
    if schedule:
        original_schedule = (schedule.schedule_time, schedule.alert_days, schedule.is_enabled, schedule.updated_by_id)

    manager_client = APIClient()
    manager_client.force_authenticate(manager)
    admin_client = APIClient()
    admin_client.force_authenticate(admin)

    report_specs = [
        ('Overview Report', 'GET', '/api/v1/reports/overview/'),
        ('Vehicles Report', 'GET', '/api/v1/reports/vehicles/'),
        ('Equipment Report', 'GET', '/api/v1/reports/equipment/'),
        ('Documents Report', 'GET', '/api/v1/reports/documents/'),
        ('Maintenance Report', 'GET', '/api/v1/reports/maintenance/'),
        ('Transfers Report', 'GET', '/api/v1/reports/transfers/'),
        ('Audit Report', 'GET', '/api/v1/reports/audit/'),
    ]
    notification_specs = [
        ('Get Notification Schedule', 'GET', '/api/v1/notifications/schedule/', None),
        ('Update Notification Schedule', 'PATCH', '/api/v1/notifications/schedule/', {'is_enabled': True, 'alert_days': 15, 'schedule_time': '10:00:00'}),
        ('List Notification Recipients', 'GET', '/api/v1/notifications/recipients/', None),
        ('Create Notification Recipient', 'POST', '/api/v1/notifications/recipients/', {'email': f'new-{suffix}@example.com', 'full_name': 'Postman Test', 'is_active': True}),
        ('List Notification Deliveries', 'GET', '/api/v1/notifications/deliveries/', None),
        ('Send Notifications Now', 'POST', '/api/v1/notifications/send-now/', None),
        ('Retry Notification Delivery', 'POST', f'/api/v1/notifications/deliveries/{delivery.id}/retry/', None),
    ]
    settings_specs = [
        ('Get Organization Settings', 'GET', '/api/v1/settings/organization/', None, manager_client),
        ('Get Notification Settings', 'GET', '/api/v1/settings/notifications/', None, admin_client),
        ('Update Notification Settings', 'PATCH', '/api/v1/settings/notifications/', {'is_enabled': True, 'alert_days': 15, 'schedule_time': '10:00:00'}, admin_client),
        ('Get Profile Settings', 'GET', '/api/v1/settings/profile/', None, admin_client),
        ('Update Profile Settings', 'PATCH', '/api/v1/settings/profile/', {'first_name': 'Postman', 'last_name': 'Tester'}, admin_client),
    ]

    reports = []
    notification_results = []
    settings = []
    statuses = []
    for name, method, path in report_specs:
        item, code = execute(manager_client, name, method, path)
        reports.append(item)
        statuses.append((name, code))
    for name, method, path, body in notification_specs:
        client = admin_client
        if name == 'Send Notifications Now':
            with patch('vehicles.api_v1.send_expiry_alerts', return_value={'status': 'sent', 'sent_count': 0}):
                item, code = execute(client, name, method, path, body)
        else:
            item, code = execute(client, name, method, path, body)
        notification_results.append(item)
        statuses.append((name, code))
    for name, method, path, body, client in settings_specs:
        item, code = execute(client, name, method, path, body)
        settings.append(item)
        statuses.append((name, code))

    if schedule and original_schedule:
        schedule.schedule_time, schedule.alert_days, schedule.is_enabled, schedule.updated_by_id = original_schedule
        schedule.save()
    EmailDeliveryLog.objects.filter(pk=delivery.pk).delete()
    EmailRecipient.objects.filter(email__contains=suffix).delete()
    UserRole.objects.filter(user__in=[manager, admin]).delete()
    manager.delete()
    admin.delete()

    paths = [
        write_collection('Reports API v1', 'Reports API requests with tested saved responses.', reports),
        write_collection('Notifications API v1', 'Notification API requests with tested saved responses.', notification_results),
        write_collection('Settings API v1', 'Settings API requests with tested saved responses.', settings),
    ]
    print(json.dumps({'collections': [str(path) for path in paths], 'request_count': len(statuses), 'statuses': statuses}, default=str))


if __name__ == '__main__':
    main()
