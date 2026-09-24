import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'asset_management.settings')
import django
django.setup()
from django.test import Client
from django.contrib.auth import get_user_model
from vehicles.models import OfficeEquipment, UserRole

User = get_user_model()

# Clean slate
OfficeEquipment.objects.all().delete()
User.objects.filter(username__in=['driver_test']).delete()

# Create driver user without staff profile but with role
driver = User.objects.create_user(username='driver_test', password='pass')
UserRole.objects.create(user=driver, role='driver')
# Create a company equipment not assigned to the driver
OfficeEquipment.objects.create(name='Company Printer', serial_number='CPR001', assigned_user='someone_else', equipment_type='printer', regional_office='Lagos')

# Use test client to get context
client = Client()
logged = client.login(username='driver_test', password='pass')
resp = client.get('/equipment/')
print('HTTP status:', resp.status_code)
print('templates:', [t.name for t in resp.templates])
ctx = resp.context
if ctx is None:
	print('No template context available; response length:', len(resp.content))
else:
	print('total_equipment:', ctx.get('total_equipment'))
	print('regional_office_counts:', ctx.get('regional_office_counts'))
	print('equipment_type_counts:', ctx.get('equipment_type_counts'))
	page_obj = ctx.get('page_obj')
	print('First page equipments count:', page_obj.paginator.count if page_obj else 0)
