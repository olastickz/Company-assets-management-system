import os
import django
import uuid
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'asset_management.settings')
django.setup()
from django.test import Client
from django.contrib.auth.models import User
from vehicles.models import StaffMember, UserRole, DriverRequest
from django.utils import timezone
from django.urls import reverse

suffix = uuid.uuid4().hex[:8]
manager_user = User.objects.create_user(username='manager_reassign_' + suffix, password='mgrpass_reassign')
UserRole.objects.create(user=manager_user, role='manager')
original_driver_user = User.objects.create_user(username='driver_orig_' + suffix, password='dpass_orig')
original_driver = StaffMember.objects.create(user=original_driver_user, staff_id='DRV08_' + suffix, first_name='Rory', last_name='Williams', department='FIELD', branch='LAGOS', driver_status='unavailable', is_active=True)
UserRole.objects.create(user=original_driver_user, role='driver')
new_driver_user = User.objects.create_user(username='driver_new_' + suffix, password='dpass_new')
new_driver = StaffMember.objects.create(user=new_driver_user, staff_id='DRV09_' + suffix, first_name='Clara', last_name='Oswald', department='FIELD', branch='LAGOS', driver_status='available', is_active=True)
UserRole.objects.create(user=new_driver_user, role='driver')
request_user = User.objects.create_user(username='staff_reassign_' + suffix, password='spass_reassign')
staff_request = StaffMember.objects.create(user=request_user, staff_id='STF024_' + suffix, first_name='Amy', last_name='Pond', department='FIELD', branch='LAGOS', is_active=True)
UserRole.objects.create(user=request_user, role='staff')
driver_request = DriverRequest.objects.create(requested_by=staff_request, requester_user=request_user, details='Urgent route support', status='assigned', assigned_driver=original_driver, assigned_by=manager_user, assigned_at=timezone.now())

print('BEFORE', original_driver.pk, driver_request.assigned_driver.pk, original_driver.driver_status, new_driver.driver_status)

c = Client()
assert c.login(username='manager_reassign_' + suffix, password='mgrpass_reassign')
url = reverse('driver_request_assign', args=[driver_request.pk])
resp = c.post(url, {'assigned_driver': new_driver.pk, 'notes': 'Switching to a closer driver'})
print('HTTP', resp.status_code, resp.content[:500])

original_driver.refresh_from_db()
new_driver.refresh_from_db()
driver_request.refresh_from_db()
print('AFTER', original_driver.pk, driver_request.assigned_driver.pk, original_driver.driver_status, new_driver.driver_status)
print('saved assigned_driver_id', driver_request.assigned_driver_id)
print('previous_driver_id', driver_request.assigned_driver_id != original_driver.pk)
