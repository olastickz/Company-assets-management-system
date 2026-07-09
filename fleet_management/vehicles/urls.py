from django.urls import path
from . import views

urlpatterns = [
    # Dashboard as main page
    path('', views.dashboard, name='dashboard'),

    # Asset detail view
    path('asset/<int:pk>/', views.vehicle_detail, name='asset_detail'),
    path('asset/<int:pk>/release/', views.release_vehicle_assignment, name='asset_release'),

    # Asset CRUD
    path('asset/add/', views.vehicle_create, name='asset_create'),
    path('asset/<int:pk>/edit/', views.vehicle_update, name='asset_update'),
    path('asset/<int:pk>/update-type/', views.vehicle_update_type, name='asset_update_type'),
    path('asset/<int:pk>/delete/', views.vehicle_delete, name='asset_delete'),

    # Maintenance CRUD
    path('asset/<int:asset_pk>/maintenance/add/', views.maintenance_create, name='maintenance_create'),
    path('equipment-maintenance/', views.equipment_maintenance_list, name='equipment_maintenance_list'),
    path('maintenance/<int:pk>/edit/', views.maintenance_update, name='maintenance_update'),
    path('maintenance/<int:pk>/delete/', views.maintenance_delete, name='maintenance_delete'),

    # Office Equipment routes
    path('equipment/', views.equipment_list, name='equipment_list'),
    path('equipment/abuja/', views.equipment_abuja, name='equipment_abuja'),
    path('equipment/iteco/', views.equipment_iteco, name='equipment_iteco'),
    path('equipment/softworks/', views.equipment_softworks, name='equipment_softworks'),
    path('equipment/<int:pk>/', views.equipment_detail, name='equipment_detail'),
    path('equipment/<int:pk>/release/', views.release_equipment_assignment, name='equipment_release'),
    path('equipment/add/', views.equipment_create, name='equipment_create'),
    path('equipment/<int:pk>/edit/', views.equipment_update, name='equipment_update'),
    path('equipment/<int:pk>/delete/', views.equipment_delete, name='equipment_delete'),

    # Office Equipment Maintenance routes
    path('equipment/<int:equipment_pk>/maintenance/add/', views.equipment_maintenance_create, name='equipment_maintenance_create'),
    path('equipment_maintenance/<int:pk>/edit/', views.equipment_maintenance_update, name='equipment_maintenance_update'),
    path('equipment_maintenance/<int:pk>/delete/', views.equipment_maintenance_delete, name='equipment_maintenance_delete'),

    # Equipment Transfer routes
    path('equipment/<int:pk>/transfer/', views.equipment_transfer, name='equipment_transfer'),
    path('equipment/<int:pk>/transfer-history/', views.equipment_transfer_history, name='equipment_transfer_history'),

    # Bulk upload routes
    path('bulk-upload-assets/', views.bulk_upload_assets, name='bulk_upload_assets'),
    path('bulk-upload-equipment/', views.bulk_upload_equipment, name='bulk_upload_equipment'),
    path('import-assets/', views.import_assets, name='import_assets'),
    path('bulk-delete-assets/', views.bulk_delete_assets, name='bulk_delete_assets'),
    path('export-selected-assets/csv/', views.export_selected_assets_csv, name='export_selected_assets_csv'),
    path('activity/', views.activity_dashboard, name='activity_dashboard'),
    path('my-assets/', views.my_assets, name='my_assets'),
    path('export/vehicles/csv/', views.export_vehicles_csv, name='export_vehicles_csv'),
    path('export/vehicles/xlsx/', views.export_vehicles_excel, name='export_vehicles_excel'),
    path('export/equipment/csv/', views.export_equipment_csv, name='export_equipment_csv'),
    path('export/equipment/xlsx/', views.export_equipment_excel, name='export_equipment_excel'),

    # Email alerts
    path('send-expiry-alerts/', views.send_expiry_alerts_view, name='send_expiry_alerts_view'),

    # Company Documents routes
    path('documents/', views.company_documents_list, name='company_documents_list'),
    path('documents/counts/', views.company_documents_counts, name='company_documents_counts'),
    path('documents/data/', views.company_documents_data, name='company_documents_data'),
    path('documents/<int:pk>/', views.company_document_detail, name='company_document_detail'),
    path('documents/add/', views.company_document_create, name='company_document_create'),
    path('documents/<int:pk>/edit/', views.company_document_edit, name='company_document_edit'),
    path('documents/<int:pk>/delete/', views.company_document_delete, name='company_document_delete'),

    # Staff registry (manager facing)
    path('staff/', views.staff_list, name='staff_list'),
    path('staff/add/', views.staff_create, name='staff_create'),
    path('staff/<int:pk>/edit/', views.staff_edit, name='staff_edit'),
    path('staff/<int:pk>/delete/', views.staff_delete, name='staff_delete'),
    path('staff/import-legacy/', views.staff_import_legacy, name='staff_import_legacy'),
    # API endpoints
    path('api/staff-autocomplete/', views.staff_autocomplete, name='staff_autocomplete'),
]