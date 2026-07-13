from .permissions import (
    get_user_role,
    is_admin,
    is_manager,
    is_driver,
    can_view_company_documents,
    can_create_company_documents,
    can_edit_company_documents,
    can_delete_company_documents,
    can_access_admin_tools,
    can_manage_staff,
    can_create_assets,
    can_create_equipment,
    can_bulk_import_assets,
    can_bulk_import_equipment,
    can_export_assets,
)


def user_roles(request):
    if not request.user.is_authenticated:
        return {
            'is_admin': False,
            'user_role': None,
            'is_manager': False,
            'is_driver': False,
            'is_staff_member': False,
            'can_view_company_documents': False,
            'can_create_company_documents': False,
            'can_edit_company_documents': False,
            'can_delete_company_documents': False,
            'can_access_admin_tools': False,
            'can_manage_staff': False,
            'can_create_assets': False,
            'can_create_equipment': False,
            'can_bulk_import_assets': False,
            'can_bulk_import_equipment': False,
            'can_export_assets': False,
            'can_create_company_document': False,
        }

    role = get_user_role(request.user)

    return {
        'is_admin': is_admin(request.user),
        'user_role': role,
        'is_staff_member': bool(getattr(request.user, 'staff_profile', None)),
        'is_manager': is_manager(request.user),
        'is_driver': is_driver(request.user),
        'can_view_company_documents': can_view_company_documents(request.user),
        'can_create_company_documents': can_create_company_documents(request.user),
        'can_edit_company_documents': can_edit_company_documents(request.user),
        'can_delete_company_documents': can_delete_company_documents(request.user),
        'can_access_admin_tools': can_access_admin_tools(request.user),
        'can_manage_staff': can_manage_staff(request.user),
        'can_create_assets': can_create_assets(request.user),
        'can_create_equipment': can_create_equipment(request.user),
        'can_bulk_import_assets': can_bulk_import_assets(request.user),
        'can_bulk_import_equipment': can_bulk_import_equipment(request.user),
        'can_export_assets': can_export_assets(request.user),
        'can_create_company_document': can_create_company_documents(request.user),
    }
