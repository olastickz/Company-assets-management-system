from random import SystemRandom

from django.db import migrations, models


SPECIALIST_ROLES = ('document_manager', 'vehicle_manager', 'equipment_manager')
ROLE_CHOICES = [
    ('admin', 'Administrator'),
    ('document_manager', 'Document Manager'),
    ('vehicle_manager', 'Vehicle Manager'),
    ('equipment_manager', 'Equipment Manager'),
    ('driver', 'Driver'),
    ('staff', 'Staff'),
]


def split_manager_accounts(apps, schema_editor):
    UserRole = apps.get_model('vehicles', 'UserRole')
    PermissionConfiguration = apps.get_model('vehicles', 'RolePermissionConfiguration')
    assignments = list(UserRole.objects.filter(role='manager').order_by('pk'))
    SystemRandom().shuffle(assignments)

    for index, assignment in enumerate(assignments):
        assignment.role = SPECIALIST_ROLES[index % len(SPECIALIST_ROLES)]
        assignment.save(update_fields=['role'])

    PermissionConfiguration.objects.filter(role='manager').delete()


class Migration(migrations.Migration):
    dependencies = [('vehicles', '0040_domain_manager_roles')]

    operations = [
        migrations.RunPython(split_manager_accounts, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='userrole',
            name='role',
            field=models.CharField(default='staff', max_length=20, choices=ROLE_CHOICES),
        ),
        migrations.AlterField(
            model_name='rolepermissionconfiguration',
            name='role',
            field=models.CharField(max_length=20, unique=True, choices=ROLE_CHOICES),
        ),
    ]