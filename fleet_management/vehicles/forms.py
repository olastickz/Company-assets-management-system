from django import forms
from django.core import validators
from django.core.exceptions import ValidationError
from .models import Asset, CompanyAsset, MaintenanceItem, OfficeEquipment, OfficeEquipmentMaintenance, CompanyDocument, StaffMember, Vehicle

# Year field removed - use `purchase_date` instead of separate year


class StaffMemberChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        branch_label = f" ({obj.branch})" if obj.branch else ''
        return f"{obj.staff_id} — {obj.full_name}{branch_label}"


class CompanyAssetForm(forms.ModelForm):
    # License plate: alphanumeric only, max 20 characters (optional for non-vehicles)
    license_plate = forms.CharField(
        max_length=20,
        required=False,
        validators=[
            validators.RegexValidator(
                regex=r'^[A-Za-z0-9\-]*$',
                message='License plate can only contain letters, numbers, and hyphens',
                code='invalid_license'
            )
        ],
        widget=forms.TextInput(attrs={
            'maxlength': '20',
            'pattern': r'[A-Za-z0-9\-]*',
            'placeholder': 'e.g., ABC-123 or ABC123 (vehicles only)',
            'title': 'Letters, numbers, and hyphens only'
        })
    )

    vin_number = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'maxlength': '100',
            'placeholder': 'Vehicle VIN (optional)',
            'title': 'Vehicle identification number'
        })
    )

    make = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'maxlength': '100',
            'placeholder': 'Vehicle make or brand',
            'title': 'Vehicle make or brand'
        })
    )

    model = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'maxlength': '100',
            'placeholder': 'Vehicle model',
            'title': 'Vehicle model'
        })
    )

    assigned_staff = StaffMemberChoiceField(
        queryset=StaffMember.objects.filter(is_active=True).order_by('staff_id'),
        required=False,
        label='Assigned Staff',
        empty_label='Select a staff member',
        widget=forms.Select(attrs={'class': 'form-control', 'data-autocomplete': 'staff'})
    )
    
    class Meta:
        model = CompanyAsset
        fields = [
            'name',
            'make',
            'model',
            'asset_type',
            'vin_number',
            'license_plate',
            'assigned_staff',
            'insurance_expiry',
            'roadworthy_expiry',
            'license_expiry',
            'hackney_permit'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'maxlength': '100', 'placeholder': 'Vehicle name'}),
            'insurance_expiry': forms.DateInput(attrs={'type': 'date'}),
            'roadworthy_expiry': forms.DateInput(attrs={'type': 'date'}),
            'license_expiry': forms.DateInput(attrs={'type': 'date'}),
            'hackney_permit': forms.DateInput(attrs={'type': 'date'}),
        }


VehicleForm = CompanyAssetForm


class MaintenanceItemForm(forms.ModelForm):
    class Meta:
        model = MaintenanceItem
        fields = '__all__'
        widgets = {
            'date_performed': forms.DateInput(attrs={'type': 'date'}),
        }


class OfficeEquipmentForm(forms.ModelForm):
    # `year_of_purchase` removed; use `purchase_date` field instead
    
    # Serial Number: alphanumeric only, max 100 characters
    serial_number = forms.CharField(
        max_length=100,
        required=False,
        validators=[
            validators.RegexValidator(
                regex=r'^[A-Za-z0-9\-]*$',
                message='Serial number can only contain letters, numbers, and hyphens',
                code='invalid_serial'
            )
        ],
        widget=forms.TextInput(attrs={
            'maxlength': '100',
            'pattern': r'[A-Za-z0-9\-]*',
            'placeholder': 'e.g., SN-123456 or ABC123XYZ',
            'title': 'Letters, numbers, and hyphens only'
        })
    )
    
    # Tag Number: alphanumeric only, max 100 characters
    tag_number = forms.CharField(
        max_length=100,
        required=False,
        validators=[
            validators.RegexValidator(
                regex=r'^[A-Za-z0-9\-]*$',
                message='Tag number can only contain letters, numbers, and hyphens',
                code='invalid_tag'
            )
        ],
        widget=forms.TextInput(attrs={
            'maxlength': '100',
            'pattern': r'[A-Za-z0-9\-]*',
            'placeholder': 'e.g., TAG-001 or IT-001-LAP',
            'title': 'Letters, numbers, and hyphens only'
        })
    )
    
    # Assigned Staff: dropdown selecting from active staff members
    assigned_staff = StaffMemberChoiceField(
        queryset=StaffMember.objects.filter(is_active=True).order_by('staff_id'),
        required=False,
        label='Assigned Staff',
        empty_label='Select a staff member',
        widget=forms.Select(attrs={
            'style': 'width:100%;',
            'class': 'form-control'
        })
    )
    
    # Quantity: numeric only, positive integers
    quantity = forms.IntegerField(
        min_value=1,
        initial=1,
        validators=[
            validators.MinValueValidator(1),
        ],
        widget=forms.NumberInput(attrs={
            'min': '1',
            'placeholder': 'Quantity (1 or more)',
            'title': 'Enter a positive number'
        })
    )
    
    class Meta:
        model = OfficeEquipment
        fields = [
            'name',
            'equipment_type',
            'description',
            'purchase_date',
            'warranty_expiry',
            'status',
            'location',
            'regional_office',
            'cost',
            'notes',
            'subsidiary',
            'serial_number',
            'tag_number',
            'assigned_staff',
            'quantity',
            'remarks',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'maxlength': '100', 'placeholder': 'Equipment name'}),
            'location': forms.TextInput(attrs={
                'maxlength': '100',
                'pattern': r'[A-Za-z0-9\s\-]*',
                'placeholder': 'e.g., Office 1 or Building A',
                'title': 'Letters, numbers, spaces, and hyphens only'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'maxlength': '500',
                'placeholder': 'Item Description, Location, QTY, Serial Number, YOP, Tag Number, User, Remarks'
            }),
            'remarks': forms.Textarea(attrs={
                'rows': 3,
                'maxlength': '500',
                'placeholder': 'Additional remarks'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'maxlength': '500',
                'placeholder': 'Notes'
            }),
            'purchase_date': forms.DateInput(attrs={'type': 'date'}),
            'warranty_expiry': forms.DateInput(attrs={'type': 'date'}),
            'subsidiary': forms.Select(attrs={'style': 'width:100%;'}),
            'equipment_type': forms.Select(attrs={'style': 'width:100%;'}),
            'status': forms.Select(attrs={'style': 'width:100%;'}),
        }


class OfficeEquipmentMaintenanceForm(forms.ModelForm):
    class Meta:
        model = OfficeEquipmentMaintenance
        fields = '__all__'
        widgets = {
            'maintenance_date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }


class EquipmentTransferForm(forms.Form):
    """Form for transferring equipment between staff members"""
    transferred_to = forms.CharField(
        max_length=100,
        label='Staff Member Name (Receiving)',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Full name of the staff member receiving the equipment',
            'required': True
        })
    )
    
    transferred_to_department = forms.CharField(
        max_length=100,
        required=False,
        label='Department (Receiving)',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Department of the new user (optional)'
        })
    )
    
    transferred_to_email = forms.EmailField(
        required=False,
        label='Email Address (Receiving)',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email of the new user (optional)'
        })
    )
    
    reason = forms.CharField(
        max_length=255,
        required=False,
        label='Reason for Transfer',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., Staff reassignment, Replacement, Upgrade'
        })
    )
    
    notes = forms.CharField(
        required=False,
        label='Additional Notes',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Any additional notes about this transfer',
            'rows': 4
        })
    )


class StaffMemberForm(forms.ModelForm):
    """Form for creating and editing staff registry entries."""
    is_active = forms.TypedChoiceField(
        choices=[(True, 'Yes'), (False, 'No')],
        coerce=lambda x: x == 'True',
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Active Staff Member',
    )

    class Meta:
        model = StaffMember
        fields = ['staff_id', 'first_name', 'last_name', 'email', 'department', 'branch', 'is_active']
        widgets = {
            'staff_id': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'branch': forms.Select(attrs={'class': 'form-control'}),
        }

class CompanyDocumentForm(forms.ModelForm):
    """Form for managing company documents with expiry tracking"""

    related_vehicle = forms.ModelChoiceField(
        queryset=CompanyAsset.objects.all().order_by('name'),
        required=False,
        label='Related Vehicle',
        empty_label='Select a vehicle',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    related_equipment = forms.ModelChoiceField(
        queryset=OfficeEquipment.objects.all().order_by('name'),
        required=False,
        label='Related Equipment',
        empty_label='Select equipment',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    related_asset = forms.ModelChoiceField(
        queryset=Asset.objects.all().order_by('name'),
        required=False,
        label='Related Asset',
        empty_label='Select an asset',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    responsible_staff = StaffMemberChoiceField(
        queryset=StaffMember.objects.filter(is_active=True).order_by('staff_id'),
        required=False,
        label='Responsible Staff',
        empty_label='Select a staff member',
        widget=forms.Select(attrs={'class': 'form-control', 'data-autocomplete': 'staff'})
    )

    class Meta:
        model = CompanyDocument
        fields = [
            'name', 'document_type', 'description',
            'related_asset', 'related_vehicle', 'related_equipment',
            'issue_date', 'expiry_date', 'renewal_date',
            'document_number', 'issuing_authority', 'status',
            'notify_days_before', 'responsible_person', 'responsible_staff', 'location', 'notes'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'document_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'related_asset': forms.Select(attrs={'class': 'form-control'}),
            'issue_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'renewal_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'document_number': forms.TextInput(attrs={'class': 'form-control'}),
            'issuing_authority': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'notify_days_before': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '365'}),
            'responsible_person': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_notify_days_before(self):
        notify_days_before = self.cleaned_data.get('notify_days_before')
        if notify_days_before is None or notify_days_before < 0:
            raise ValidationError('Notification window must be zero or greater')
        return notify_days_before

    def clean(self):
        cleaned_data = super().clean()
        issue_date = cleaned_data.get('issue_date')
        expiry_date = cleaned_data.get('expiry_date')
        related_vehicle = cleaned_data.get('related_vehicle')

        if issue_date and expiry_date and expiry_date < issue_date:
            self.add_error('expiry_date', 'Expiry date must be after issue date')

        related_asset = cleaned_data.get('related_asset')
        related_equipment = cleaned_data.get('related_equipment')

        if related_asset and related_vehicle:
            self.add_error('related_asset', 'A document may only be linked to one asset at a time.')
            self.add_error('related_vehicle', 'A document may only be linked to one asset at a time.')

        if related_asset and related_equipment:
            self.add_error('related_asset', 'A document may only be linked to one asset at a time.')
            self.add_error('related_equipment', 'A document may only be linked to one asset at a time.')

        if related_vehicle and related_equipment:
            self.add_error('related_vehicle', 'A document may only be linked to one asset at a time.')
            self.add_error('related_equipment', 'A document may only be linked to one asset at a time.')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.pk and instance.related_equipment and (self.cleaned_data.get('related_asset') or self.cleaned_data.get('related_vehicle')):
            instance.related_equipment = None
        if commit:
            instance.save()
            self.save_m2m()
        return instance
