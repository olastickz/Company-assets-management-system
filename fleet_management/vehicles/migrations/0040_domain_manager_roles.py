from django.db import migrations, models


ROLE_CHOICES = [
    ('admin', 'Administrator'),
    ('manager', 'Manager'),
    ('document_manager', 'Document Manager'),
    ('vehicle_manager', 'Vehicle Manager'),
    ('equipment_manager', 'Equipment Manager'),
    ('driver', 'Driver'),
    ('staff', 'Staff'),
]

ACTIONS = ('view', 'create', 'edit', 'delete', 'approve', 'export')
NEW_MODULES = ('vehicle_maintenance', 'equipment_maintenance')


def seed_domain_manager_roles(apps, schema_editor):
    Configuration = apps.get_model('vehicles', 'RolePermissionConfiguration')
    modules = (
        'vehicles', 'equipment', 'staff', 'documents', 'maintenance',
        'vehicle_maintenance', 'equipment_maintenance', 'work_orders',
        'transfers', 'requests', 'audits', 'reports', 'notifications', 'settings',
    )

    for configuration in Configuration.objects.all():
        saved_modules = configuration.modules or {}
        for module in NEW_MODULES:
            saved_modules.setdefault(module, {action: False for action in ACTIONS})
        if configuration.role == 'manager':
            for module in NEW_MODULES:
                saved_modules[module] = {action: True for action in ACTIONS}
        configuration.modules = saved_modules
        configuration.save(update_fields=['modules'])

    scoped_grants = {
        'document_manager': {'documents': set(ACTIONS)},
        'vehicle_manager': {
            'vehicles': set(ACTIONS),
            'vehicle_maintenance': set(ACTIONS),
            'requests': {'view', 'approve'},
        },
        'equipment_manager': {
            'equipment': set(ACTIONS),
            'equipment_maintenance': set(ACTIONS),
            'work_orders': set(ACTIONS),
            'transfers': set(ACTIONS),
        },
    }
    for role, module_grants in scoped_grants.items():
        grants = {
            module: {
                action: action in module_grants.get(module, set())
                for action in ACTIONS
            }
            for module in modules
        }
        Configuration.objects.get_or_create(
            role=role,
            defaults={
                'modules': grants,
                'approval_authority': {
                    'level_1': role == 'vehicle_manager',
                    'level_2': False,
                },
            },
        )


class Migration(migrations.Migration):
    dependencies = [('vehicles', '0039_seed_role_permission_defaults')]

    operations = [
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
        migrations.RunPython(seed_domain_manager_roles, migrations.RunPython.noop),
    ]