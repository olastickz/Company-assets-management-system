from .permissions import get_user_role, is_admin


def user_roles(request):
    if not request.user.is_authenticated:
        return {
            'is_admin': False,
            'user_role': None,
        }

    role = get_user_role(request.user)
    return {
        'is_admin': is_admin(request.user),
        'user_role': role,
    }
