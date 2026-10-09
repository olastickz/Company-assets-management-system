from django.urls import path, include
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.reverse import reverse
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from .api import (
    CompanyDocumentViewSet,
    VehicleViewSet,
    OfficeEquipmentViewSet,
    EquipmentWorkOrderViewSet,
    get_token,
    staff_api,
    staff_detail_api,
    asset_detail_api,
    asset_assign_api,
    asset_release_api,
    asset_history_api,
    documents_api,
    document_detail_api,
    equipment_maintenance_api,
    equipment_maintenance_detail_api,
    vehicle_maintenance_api,
    vehicle_maintenance_detail_api,
    equipment_transfers_api,
    equipment_transfer_detail_api,
    driver_requests_api,
    driver_request_detail_api,
    driver_request_assign_api,
    me_api,
    password_reset_api,
    export_vehicles_csv_api,
    export_equipment_csv_api,
    bulk_upload_assets_api,
    bulk_upload_equipment_api,
)

router = DefaultRouter()
router.register(r'vehicles', VehicleViewSet, basename='vehicle')
router.register(r'equipment', OfficeEquipmentViewSet, basename='equipment')
router.register(r'equipment-work-orders', EquipmentWorkOrderViewSet, basename='equipment-work-order')
router.register(r'documents', CompanyDocumentViewSet, basename='document')

@api_view(['GET'])
@permission_classes([AllowAny])
def api_root(request, format=None):
    return Response({
        'vehicles': reverse('vehicle-list', request=request, format=format),
        'equipment': reverse('equipment-list', request=request, format=format),
        'equipment-work-orders': reverse('equipment-work-order-list', request=request, format=format),
        'documents': reverse('document-list', request=request, format=format),
        'get-token': reverse('get-token', request=request, format=format),
    })

urlpatterns = [
    path('', api_root, name='api-root'),
    path('', include(router.urls)),
    path('get-token/', get_token, name='get-token'),
    path('staff/', staff_api, name='staff-list'),
    path('staff/<int:pk>/', staff_detail_api, name='staff-detail'),
    path('asset/<int:pk>/', asset_detail_api, name='asset-detail'),
    path('asset/<int:pk>/assign/', asset_assign_api, name='asset-assign'),
    path('asset/<int:pk>/release/', asset_release_api, name='asset-release'),
    path('asset/<int:pk>/history/', asset_history_api, name='asset-history'),
    path('documents/', documents_api, name='documents-list'),
    path('documents/<int:pk>/', document_detail_api, name='documents-detail'),
    path('equipment-maintenance/', equipment_maintenance_api, name='equipment-maintenance-list'),
    path('equipment-maintenance/<int:pk>/', equipment_maintenance_detail_api, name='equipment-maintenance-detail'),
    path('vehicle-maintenance/', vehicle_maintenance_api, name='vehicle-maintenance-list'),
    path('vehicle-maintenance/<int:pk>/', vehicle_maintenance_detail_api, name='vehicle-maintenance-detail'),
    path('equipment-transfers/', equipment_transfers_api, name='equipment-transfer-list'),
    path('equipment-transfers/<int:pk>/', equipment_transfer_detail_api, name='equipment-transfer-detail'),
    path('driver-requests/', driver_requests_api, name='driver-request-list'),
    path('driver-requests/<int:pk>/', driver_request_detail_api, name='driver-request-detail'),
    path('driver-requests/<int:pk>/assign/', driver_request_assign_api, name='driver-request-assign'),
    path('me/', me_api, name='me'),
    path('password-reset/', password_reset_api, name='password-reset'),
    path('export/vehicles/csv/', export_vehicles_csv_api, name='export-vehicles-csv'),
    path('export/equipment/csv/', export_equipment_csv_api, name='export-equipment-csv'),
    path('bulk-upload-assets/', bulk_upload_assets_api, name='bulk-upload-assets'),
    path('bulk-upload-equipment/', bulk_upload_equipment_api, name='bulk-upload-equipment'),
]
