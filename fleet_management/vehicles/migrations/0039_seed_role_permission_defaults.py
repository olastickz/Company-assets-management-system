from django.db import migrations


MODULES = (
    'vehicles', 'equipment', 'staff', 'documents', 'maintenance',
    'work_orders', 'transfers', 'requests', 'audits', 'reports',
    'notifications', 'settings',
)
ACTIONS = ('view', 'create', 'edit', 'delete', 'approve', 'export')


def seed_role_permissions(apps, schema_editor):
    Configuration = apps.get_model('vehicles', 'RolePermissionConfiguration')
    defaults = {
        role: {
            module: {action: False for action in ACTIONS}
            for module in MODULES
        }
        for role in ('manager', 'driver', 'staff')
    }

    def grant(role, module, *actions):
        for action in actions:
            defaults[role][module][action] = True

    for role in defaults:
        grant(role, 'vehicles', 'view')
        grant(role, 'equipment', 'view')
        grant(role, 'maintenance', 'view')
        grant(role, 'requests', 'view', 'create')
        grant(role, 'transfers', 'view', 'create')
        grant(role, 'settings', 'view', 'edit')

    for role in ('manager',):
        grant(role, 'documents', 'view', 'edit', 'delete')
        grant(role, 'maintenance', 'create', 'edit', 'delete')
        grant(role, 'work_orders', 'view', 'create', 'edit', 'delete')
        grant(role, 'requests', 'approve')
        grant(role, 'audits', 'view')
        grant(role, 'reports', 'view')
        grant(role, 'notifications', 'view')

    grant('staff', 'maintenance', 'view')
    grant('driver', 'maintenance', 'view')

    admin_grants = {
        module: {action: True for action in ACTIONS}
        for module in MODULES
    }

    for role, grants in defaults.items():
        configuration, created = Configuration.objects.get_or_create(
            role=role,
            defaults={'modules': grants, 'approval_authority': {
                'level_1': role == 'manager', 'level_2': False,
            }},
        )
        if created:
            continue
        saved_modules = configuration.modules or {}
        for module, actions in grants.items():
            saved_actions = saved_modules.setdefault(module, {})
            for action, enabled in actions.items():
                saved_actions.setdefault(action, enabled)
        configuration.modules = saved_modules
        saved_authority = configuration.approval_authority or {}
        saved_authority.setdefault('level_1', role == 'manager')
        saved_authority.setdefault('level_2', False)
        configuration.approval_authority = saved_authority
        configuration.save(update_fields=['modules', 'approval_authority'])

    Configuration.objects.get_or_create(
        role='admin',
        defaults={'modules': admin_grants, 'approval_authority': {
            'level_1': True, 'level_2': True,
        }},
    )


class Migration(migrations.Migration):
    dependencies = [('vehicles', '0038_rolepermissionconfiguration')]

    operations = [migrations.RunPython(seed_role_permissions, migrations.RunPython.noop)]