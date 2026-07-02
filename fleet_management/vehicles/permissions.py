"""
Permission helpers for role-based access control
"""
from functools import wraps
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from .models import UserRole, AuditLog


def get_user_role(user):
    """Get the role of a user, returns 'staff' if not set"""
    if not user.is_authenticated:
        return None
    try:
        return user.role.role
    except UserRole.DoesNotExist:
        # Default to staff if role not set
        UserRole.objects.get_or_create(user=user, defaults={'role': 'staff'})
        return 'staff'


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
