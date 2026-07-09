from .permissions import get_user_role, is_admin, is_manager, is_driver


def user_roles(request):
    if not request.user.is_authenticated:
        return {
            'is_admin': False,
            'user_role': None,
            'is_manager': False,
            'is_driver': False,
            'is_staff_member': False,
        }

    role = get_user_role(request.user)

    return {
        'is_admin': is_admin(request.user),
        'user_role': role,
        'is_staff_member': bool(getattr(request.user, 'staff_profile', None)),
        'is_manager': is_manager(request.user),
        'is_driver': is_driver(request.user),
        'can_create_company_document': is_admin(request.user),
    }
