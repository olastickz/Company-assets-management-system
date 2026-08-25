from rest_framework import viewsets, permissions, status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.authentication import BasicAuthentication, TokenAuthentication
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from .models import Vehicle, OfficeEquipment, Asset, StaffMember, CompanyDocument, OfficeEquipmentMaintenance
from .permissions import get_user_role, is_admin
from .serializers import (
    VehicleSerializer,
    OfficeEquipmentSerializer,
    AssetSerializer,
    StaffMemberSerializer,
    CompanyDocumentSerializer,
    OfficeEquipmentMaintenanceSerializer,
)
from . import views


class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.all().order_by('-updated_at')
    serializer_class = VehicleSerializer
    permission_classes = [permissions.IsAuthenticated]


class OfficeEquipmentViewSet(viewsets.ModelViewSet):
    queryset = OfficeEquipment.objects.all().order_by('-updated_at')
    serializer_class = OfficeEquipmentSerializer
    permission_classes = [permissions.IsAuthenticated]


@api_view(['POST'])
@authentication_classes([TokenAuthentication, BasicAuthentication])
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


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def staff_api(request):
    if request.method == 'GET':
        queryset = StaffMember.objects.all().order_by('staff_id')
        serializer = StaffMemberSerializer(queryset, many=True)
        return Response(serializer.data)

    serializer = StaffMemberSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def staff_detail_api(request, pk):
    staff = get_object_or_404(StaffMember, pk=pk)

    if request.method == 'GET':
        serializer = StaffMemberSerializer(staff)
        return Response(serializer.data)

    if request.method == 'PUT':
        serializer = StaffMemberSerializer(staff, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    staff.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def asset_detail_api(request, pk):
    asset = get_object_or_404(Asset, pk=pk)

    if request.method == 'GET':
        serializer = AssetSerializer(asset)
        return Response(serializer.data)

    if request.method == 'PUT':
        serializer = AssetSerializer(asset, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    asset.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def asset_assign_api(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    staff_id = request.data.get('staff_id') or request.data.get('staff_member_id') or request.data.get('assigned_staff_id')

    if not staff_id:
        return Response({'detail': 'staff_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    staff = get_object_or_404(StaffMember, pk=staff_id)
    asset.assigned_staff = staff
    asset.save(update_fields=['assigned_staff'])

    related_company_asset = getattr(asset, 'company_asset', None)
    if related_company_asset:
        related_company_asset.assigned_staff = staff
        related_company_asset.save(update_fields=['assigned_staff'])

    return Response({'detail': 'Asset assigned successfully', 'asset': AssetSerializer(asset).data})


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def asset_release_api(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    asset.assigned_staff = None
    asset.save(update_fields=['assigned_staff'])

    related_company_asset = getattr(asset, 'company_asset', None)
    if related_company_asset:
        related_company_asset.assigned_staff = None
        related_company_asset.save(update_fields=['assigned_staff'])

    return Response({'detail': 'Asset assignment released successfully', 'asset': AssetSerializer(asset).data})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def asset_history_api(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    history = []
    for entry in asset.assignments.all().order_by('-assigned_at'):
        history.append({
            'id': entry.pk,
            'staff_member': entry.staff_member.pk if entry.staff_member else None,
            'staff_name': str(entry.staff_member) if entry.staff_member else None,
            'assigned_at': entry.assigned_at.isoformat() if entry.assigned_at else None,
            'released_at': entry.released_at.isoformat() if entry.released_at else None,
            'is_active': entry.is_active,
        })
    return Response(history)


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def documents_api(request):
    if request.method == 'GET':
        queryset = CompanyDocument.objects.all().order_by('-created_at')
        serializer = CompanyDocumentSerializer(queryset, many=True)
        return Response(serializer.data)

    serializer = CompanyDocumentSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def document_detail_api(request, pk):
    document = get_object_or_404(CompanyDocument, pk=pk)

    if request.method == 'GET':
        serializer = CompanyDocumentSerializer(document)
        return Response(serializer.data)

    if request.method in ['PUT', 'PATCH']:
        serializer = CompanyDocumentSerializer(document, data=request.data, partial=(request.method == 'PATCH'))
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    document.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def equipment_maintenance_api(request):
    if request.method == 'GET':
        queryset = OfficeEquipmentMaintenance.objects.all().order_by('-maintenance_date')
        serializer = OfficeEquipmentMaintenanceSerializer(queryset, many=True)
        return Response(serializer.data)

    serializer = OfficeEquipmentMaintenanceSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def equipment_maintenance_detail_api(request, pk):
    maintenance = get_object_or_404(OfficeEquipmentMaintenance, pk=pk)

    if request.method == 'GET':
        serializer = OfficeEquipmentMaintenanceSerializer(maintenance)
        return Response(serializer.data)

    if request.method in ['PUT', 'PATCH']:
        serializer = OfficeEquipmentMaintenanceSerializer(maintenance, data=request.data, partial=(request.method == 'PATCH'))
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    maintenance.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def me_api(request):
    return Response({
        'id': request.user.pk,
        'username': request.user.username,
        'email': request.user.email,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
        'role': get_user_role(request.user),
    })


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def password_reset_api(request):
    email = request.data.get('email', '').strip()
    if not email:
        return Response({'detail': 'email is required'}, status=status.HTTP_400_BAD_REQUEST)

    form = PasswordResetForm(data={'email': email})
    if form.is_valid():
        form.save(request=request, use_https=request.is_secure(), email_template_name='registration/password_reset_email.html')
        return Response({'detail': 'Password reset email sent if the account exists.'})

    return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def export_vehicles_csv_api(request):
    return views.export_vehicles_csv(request)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def export_equipment_csv_api(request):
    return views.export_equipment_csv(request)


@api_view(['POST'])
@authentication_classes([TokenAuthentication, BasicAuthentication])
@permission_classes([permissions.IsAuthenticated])
def bulk_upload_assets_api(request):
    if not is_admin(request.user):
        return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    return views.bulk_upload_assets.__wrapped__(request)


@api_view(['POST'])
@authentication_classes([TokenAuthentication, BasicAuthentication])
@permission_classes([permissions.IsAuthenticated])
def bulk_upload_equipment_api(request):
    if not is_admin(request.user):
        return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
    return views.bulk_upload_equipment.__wrapped__(request)
