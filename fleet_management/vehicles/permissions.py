"""
Permission helpers for role-based access control
"""
from functools import wraps
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from rest_framework.permissions import BasePermission
from .models import RolePermissionConfiguration, UserRole, AuditLog


def get_user_role(user):
    """Get the role of a user, returns 'staff' if not set"""
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return 'admin'
    try:
        return user.role.role
    except UserRole.DoesNotExist:
        # Default to staff if role not set
        UserRole.objects.get_or_create(user=user, defaults={'role': 'staff'})
        return 'staff'


def has_role_permission(user, module, action, approval_level=None):
    if not user.is_authenticated:
        return False
    if user.is_superuser or get_user_role(user) == 'admin':
        return True
    configuration = RolePermissionConfiguration.objects.filter(
        role=get_user_role(user)
    ).only('modules').first()
    if configuration is None:
        return False
    if not configuration.modules.get(module, {}).get(action, False):
        return False
    if approval_level:
        return bool(configuration.approval_authority.get(approval_level, False))
    return True


class RoleMatrixPermission(BasePermission):
    permission_module = None
    permission_action_map = {}
    VIEWSET_ACTIONS = {
        'list': 'view',
        'retrieve': 'view',
        'create': 'create',
        'update': 'edit',
        'partial_update': 'edit',
        'destroy': 'delete',
    }
    METHOD_ACTIONS = {
        'GET': 'view',
        'HEAD': 'view',
        'OPTIONS': 'view',
        'POST': 'create',
        'PUT': 'edit',
        'PATCH': 'edit',
        'DELETE': 'delete',
    }

    @classmethod
    def for_module(cls, module, action_map=None):
        return type(
            f'{module.title().replace("_", "")}RoleMatrixPermission',
            (cls,),
            {
                'permission_module': module,
                'permission_action_map': action_map or {},
            },
        )

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        module = getattr(view, 'permission_module', self.permission_module)
        if not module:
            return True
        action_map = getattr(view, 'permission_action_map', self.permission_action_map)
        action = action_map.get(request.method)
        if action is None:
            action = self.VIEWSET_ACTIONS.get(getattr(view, 'action', None))
        if action is None:
            action = self.METHOD_ACTIONS.get(request.method)
        approval_level = None
        if isinstance(action, tuple):
            action, approval_level = action
        return bool(action and has_role_permission(
            request.user, module, action, approval_level=approval_level
        ))


def is_admin(user):
    """Check if user is an admin"""
    if user.is_superuser:
        return True
    return get_user_role(user) == 'admin'


def is_manager(user):
    """Check if user is a manager or higher"""
    role = get_user_role(user)
    return role in ['admin', 'manager']


def is_driver(user):
    """Check if user is a driver"""
    return get_user_role(user) == 'driver'


def can_view_company_documents(user):
    """Managers and admins can view the company documents workspace."""
    return is_manager(user)


def can_create_company_documents(user):
    """Only administrators can create company documents."""
    return is_admin(user)


def can_edit_company_documents(user):
    """Managers and admins can update company document metadata."""
    return is_manager(user)


def can_delete_company_documents(user):
    """Managers and admins can delete company documents through the existing management flow."""
    return is_manager(user)


def can_request_driver(user):
    """Drivers, staff, and managers can request driver assignment support."""
    return get_user_role(user) in ['driver', 'staff', 'manager']


def can_assign_driver(user):
    """Only managers and admins can assign drivers to requests."""
    return is_manager(user)


def can_access_admin_tools(user):
    """Admin-only tools such as staff management, bulk imports, and exports."""
    return is_admin(user)


def can_manage_staff(user):
    """Staff directory and staff-management surfaces are restricted to administrators."""
    return is_admin(user)


def can_create_assets(user):
    """Asset creation is an administrator-only workflow."""
    return is_admin(user)


def can_create_equipment(user):
    """Equipment creation is an administrator-only workflow."""
    return is_admin(user)


def can_bulk_import_assets(user):
    """Bulk asset import remains an administrator-only capability."""
    return is_admin(user)


def can_bulk_import_equipment(user):
    """Bulk equipment import remains an administrator-only capability."""
    return is_admin(user)


def can_export_assets(user):
    """CSV and Excel exports are administrator-only operational tools."""
    return is_admin(user)


def is_staff(user):
    """Check if user is staff or higher"""
    role = get_user_role(user)
    return role in ['admin', 'manager', 'staff']


def log_audit(user, action, model_name, object_id=None, description=None, ip_address=None):
    """Log a user action for audit trail"""
    try:
        AuditLog.objects.create(
            user=user,
            action=action,
            model_name=model_name,
            object_id=object_id,
            description=description,
            ip_address=ip_address
        )
    except Exception as e:
        print(f"Error logging audit: {e}")


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def require_role(*allowed_roles):
    """Decorator to require specific roles for a view"""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            user_role = get_user_role(request.user)
            if user_role not in allowed_roles:
                log_audit(
                    request.user,
                    'permission_denied',
                    'view',
                    description=f"Attempted access to {view_func.__name__}",
                    ip_address=get_client_ip(request)
                )
                return HttpResponseForbidden(
                    f'Access denied. Required role(s): {", ".join(allowed_roles)}. Your role: {user_role}'
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_admin(view_func):
    """Decorator to require admin role"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_admin(request.user):
            log_audit(
                request.user,
                'permission_denied',
                'admin_view',
                description=f"Attempted admin access: {view_func.__name__}",
                ip_address=get_client_ip(request)
            )
            return HttpResponseForbidden('Admin access required')
        return view_func(request, *args, **kwargs)
    return wrapper


def require_manager(view_func):
    """Decorator to require manager role or higher"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_manager(request.user):
            log_audit(
                request.user,
                'permission_denied',
                'manager_view',
                description=f"Attempted manager access: {view_func.__name__}",
                ip_address=get_client_ip(request)
            )
            return HttpResponseForbidden('Manager access required')
        return view_func(request, *args, **kwargs)
    return wrapper
