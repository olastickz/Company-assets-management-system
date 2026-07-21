from rest_framework import viewsets, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
from .models import Vehicle, OfficeEquipment
from .serializers import VehicleSerializer, OfficeEquipmentSerializer


class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.all().order_by('-updated_at')
    serializer_class = VehicleSerializer
    permission_classes = [permissions.IsAuthenticated]


class OfficeEquipmentViewSet(viewsets.ModelViewSet):
    queryset = OfficeEquipment.objects.all().order_by('-updated_at')
    serializer_class = OfficeEquipmentSerializer
    permission_classes = [permissions.IsAuthenticated]


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def get_token(request):
    """
    Get authentication token by providing username and password.
    Usage: POST /api/get-token/ with {"username": "user", "password": "pass"}
    Returns: {"token": "your-token-here"}
    """
    username = request.data.get('username')
    password = request.data.get('password')
    
    if not username or not password:
        return Response(
            {'error': 'username and password required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    user = None
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not user.check_password(password):
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    token, created = Token.objects.get_or_create(user=user)
    return Response({'token': str(token)})
