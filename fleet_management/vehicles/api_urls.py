from django.urls import path, include
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.reverse import reverse
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from .api import VehicleViewSet, OfficeEquipmentViewSet, get_token

router = DefaultRouter()
router.register(r'vehicles', VehicleViewSet, basename='vehicle')
router.register(r'equipment', OfficeEquipmentViewSet, basename='equipment')

@api_view(['GET'])
@permission_classes([AllowAny])
def api_root(request, format=None):
    return Response({
        'vehicles': reverse('vehicle-list', request=request, format=format),
        'equipment': reverse('equipment-list', request=request, format=format),
        'get-token': reverse('get-token', request=request, format=format),
    })

urlpatterns = [
    path('', api_root, name='api-root'),
    path('', include(router.urls)),
    path('get-token/', get_token, name='get-token'),
]
