from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from vehicles.models import StaffMember, DriverRequest, UserRole
from django.utils import timezone

class Command(BaseCommand):
    help = 'Smoke test: create users, staff, driver request, assign and reassign drivers and print statuses'

    def handle(self, *args, **options):
        manager, _ = User.objects.get_or_create(username='smoke_manager')
        manager.set_password('pass')
        manager.save()
        UserRole.objects.update_or_create(user=manager, defaults={'role': 'manager'})

        u1, _ = User.objects.get_or_create(username='smoke_requester')
        UserRole.objects.update_or_create(user=u1, defaults={'role': 'staff'})

        s1, _ = StaffMember.objects.update_or_create(staff_id='SMOKE001', defaults={'first_name':'Alice','last_name':'Driver','driver_status':'available','user':u1})
        s2, _ = StaffMember.objects.update_or_create(staff_id='SMOKE002', defaults={'first_name':'Bob','last_name':'Driver','driver_status':'available'})

        req = DriverRequest.objects.create(requested_by=s1, requester_user=u1, details='Smoke: Need driver')
        self.stdout.write(f'Created request id {req.pk} status {req.status}')

        # assign s2
        prev_id = req.assigned_driver_id
        req.assigned_driver = s2
        req.assigned_by = manager
        req.assigned_at = timezone.now()
        req.status = 'assigned'
        req.save()

        s1.refresh_from_db()
        s2.refresh_from_db()
        self.stdout.write(f's1.driver_status {s1.driver_status}')
        self.stdout.write(f's2.driver_status {s2.driver_status}')

        # reassign to s1 and check restoration
        previous_driver_id = req.assigned_driver_id
        req.assigned_driver = s1
        req.assigned_by = manager
        req.assigned_at = timezone.now()
        req.status = 'assigned'
        req.save()

        prev = StaffMember.objects.filter(pk=previous_driver_id).first()
        prev.refresh_from_db()
        s1.refresh_from_db()
        self.stdout.write(f'after reassign prev.driver_status {prev.driver_status if prev else "<none>"}')
        self.stdout.write(f'after reassign s1.driver_status {s1.driver_status}')
