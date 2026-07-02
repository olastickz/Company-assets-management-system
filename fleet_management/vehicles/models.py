from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class CompanyAsset(models.Model):
    ASSET_TYPE_CHOICES = [
        ('car', 'Car'),
        ('truck', 'Truck'),
        ('van', 'Van'),
        ('bus', 'Bus'),
        ('motorbike', 'Motorbike'),
    ]

    VEHICLE_TYPE_CHOICES = ASSET_TYPE_CHOICES

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('pending_certification', 'Pending Certification'),
        ('inactive', 'Inactive'),
    ]

    # Basic info
    name = models.CharField(max_length=100, default='Unknown Asset')
    license_plate = models.CharField(max_length=20, unique=True, default='UNKNOWN', blank=True, null=True, help_text='License plate for vehicles')
    vin_number = models.CharField(max_length=100, unique=True, blank=True, null=True, help_text='Vehicle VIN number')
    make = models.CharField(max_length=100, blank=True, null=True, help_text='Vehicle make or brand')
    model = models.CharField(max_length=100, blank=True, null=True, help_text='Vehicle model')
    asset_type = models.CharField(max_length=20, choices=ASSET_TYPE_CHOICES, default='car')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='active')

    # Expiry fields (fully optional)
    insurance_expiry = models.DateField(blank=True, null=True)
    roadworthy_expiry = models.DateField(blank=True, null=True)
    license_expiry = models.DateField(blank=True, null=True)
    hackney_permit = models.DateField(blank=True, null=True)

    # Cost field
    cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    assigned_staff = models.ForeignKey(
        'StaffMember',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='company_assets',
        help_text='Select an existing staff member assigned to this asset'
    )
    asset = models.OneToOneField(
        'Asset',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='company_asset',
        help_text='Linked asset record for this asset'
    )

    @property
    def vehicle_type(self):
        return self.asset_type

    @vehicle_type.setter
    def vehicle_type(self, value):
        self.asset_type = value

    def get_vehicle_type_display(self):
        return self.get_asset_type_display()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def assigned_to_display(self):
        if self.assigned_staff:
            return str(self.assigned_staff)
        return 'Unassigned'

    def __str__(self):
        title_parts = []
        if self.make:
            title_parts.append(self.make)
        if self.model:
            title_parts.append(self.model)
        if not title_parts:
            title_parts.append(self.name)

        descriptor = ' '.join(title_parts)
        plate = f" ({self.license_plate})" if self.license_plate else ""
        vin = f" · VIN: {self.vin_number}" if self.vin_number else ""
        return f"{descriptor}{plate}{vin}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.asset:
            asset_name = self.make or self.name
            if self.model:
                asset_name = f"{asset_name} {self.model}".strip()
            plate = f" ({self.license_plate})" if self.license_plate else ""
            asset = Asset.objects.create(
                name=f"{asset_name}{plate}",
                asset_type='vehicle',
                description=self.get_asset_type_display(),
                status=self.status,
                assigned_staff=self.assigned_staff,
            )
            self.asset = asset
            super().save(update_fields=['asset'])

    def get_status(self, field_name):
        """Return 'expired', 'expiring', or 'safe' for the given date field"""
        date_field = getattr(self, field_name)
        if not date_field:
            return 'unknown'
        today = timezone.now().date()
        if date_field < today:
            return 'expired'
        elif date_field <= today + timezone.timedelta(days=30):
            return 'expiring'
        else:
            return 'safe'


Vehicle = CompanyAsset


class MaintenanceItem(models.Model):
    vehicle = models.ForeignKey(CompanyAsset, on_delete=models.CASCADE, related_name='maintenance_items', null=True, blank=True)
    description = models.CharField(max_length=255, default='General Maintenance')
    # Fully migration-friendly: optional for existing rows, auto-set today for new rows
    date_performed = models.DateField(blank=True, null=True, auto_now_add=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        vehicle_name = self.vehicle.name if self.vehicle else 'Unknown'
        return f"{vehicle_name} - {self.description} ({self.date_performed})"


class OfficeEquipment(models.Model):
    EQUIPMENT_TYPE_CHOICES = [
        ('computer', 'Computer'),
        ('laptop', 'Laptop'),
        ('printer', 'Printer'),
        ('scanner', 'Scanner'),
        ('copier', 'Copier'),
        ('ac', 'Air Conditioner'),
        ('generator', 'Generator'),
        ('furniture', 'Furniture'),
        ('phone', 'Phone/Communication'),
        ('appliance', 'Appliance'),
        ('safety', 'Safety Equipment'),
        ('network', 'Network Equipment'),
        ('electronics', 'Electronics'),
        ('office_supplies', 'Office Supplies'),
        ('other', 'Other'),
    ]

    SUBSIDIARY_CHOICES = [
        ('ITECO', 'ITECO'),
        ('Softworks', 'Softworks'),
        ('Telnet', 'Telnet'),
        ('Other', 'Other'),
    ]
    
    REGIONAL_OFFICE_CHOICES = [
        ('Lagos', 'Telnet Lagos'),
        ('Abuja', 'Telnet Abuja'),
        ('Port Harcourt', 'Telnet Port Harcourt'),
    ]

    name = models.CharField(max_length=100, default='Unknown Equipment')
    equipment_type = models.CharField(max_length=50, choices=EQUIPMENT_TYPE_CHOICES, default='other')
    description = models.TextField(blank=True, null=True)
    purchase_date = models.DateField(blank=True, null=True)
    warranty_expiry = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=50, default='active', choices=[('active', 'Active'), ('pending_certification', 'Pending Certification'), ('inactive', 'Inactive'), ('damaged', 'Damaged')])
    location = models.CharField(max_length=100, blank=True, null=True, help_text='Specific office/building/room location')
    regional_office = models.CharField(max_length=50, choices=REGIONAL_OFFICE_CHOICES, default='Lagos', help_text='Main regional Telnet office')
    cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # Laptop-specific fields
    subsidiary = models.CharField(max_length=50, choices=SUBSIDIARY_CHOICES, default='Other', blank=True)
    serial_number = models.CharField(max_length=100, blank=True, null=True)
    tag_number = models.CharField(max_length=100, blank=True, null=True)
    assigned_user = models.CharField(max_length=100, blank=True, null=True)
    assigned_staff = models.ForeignKey(
        'StaffMember',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='equipment',
        help_text='Select an existing staff member for this equipment assignment'
    )
    asset = models.OneToOneField(
        'Asset',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='equipment',
        help_text='Linked asset record for this equipment'
    )
    quantity = models.IntegerField(default=1)
    remarks = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def assigned_to_display(self):
        if self.assigned_staff:
            return str(self.assigned_staff)
        return self.assigned_user or 'Unassigned'

    def __str__(self):
        return f"{self.name} ({self.equipment_type})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.asset:
            asset = Asset.objects.create(
                name=f"{self.name} ({self.equipment_type})",
                asset_type='equipment',
                description=self.description or self.get_equipment_type_display(),
                status=self.status,
                assigned_staff=self.assigned_staff,
            )
            self.asset = asset
            super().save(update_fields=['asset'])


class OfficeEquipmentMaintenance(models.Model):
    equipment = models.ForeignKey(OfficeEquipment, on_delete=models.CASCADE, related_name='maintenance_records')
    description = models.CharField(max_length=255, default='General Maintenance')
    maintenance_date = models.DateField(auto_now_add=True)
    due_date = models.DateField(blank=True, null=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.equipment.name} - {self.description} ({self.maintenance_date})"


# ========================
# Role-Based Access Control
# ========================
class UserRole(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('manager', 'Manager'),
        ('driver', 'Driver'),
        ('staff', 'Staff'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='role')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='staff')
    department = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"


class StaffMember(models.Model):
    """Record staff identities for equipment and document assignment."""
    DEPARTMENT_CHOICES = [
        ('ABS', 'ABS'),
        ('ITECO', 'ITECO'),
        ('SOFTWORKS', 'SOFTWORKS'),
        ('HR', 'HR'),
        ('MANAGEMENT', 'MANAGEMENT'),
    ]

    BRANCH_CHOICES = [
        ('LAGOS', 'LAGOS'),
        ('ABUJA', 'ABUJA'),
        ('PORT_HARCOURT', 'Port Harcourt'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_profile',
        help_text='Optional linked Django user account'
    )
    staff_id = models.CharField(max_length=50, unique=True, help_text='Unique staff ID or employee number')
    first_name = models.CharField(max_length=100, help_text='Staff first name')
    last_name = models.CharField(max_length=100, help_text='Staff last name')
    email = models.EmailField(blank=True, null=True)
    department = models.CharField(
        max_length=50,
        choices=DEPARTMENT_CHOICES,
        blank=True,
        null=True,
        help_text='Staff department within Telnet'
    )
    branch = models.CharField(
        max_length=50,
        choices=BRANCH_CHOICES,
        blank=True,
        null=True,
        help_text='Primary Telnet branch'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['staff_id', 'last_name', 'first_name']
        verbose_name = 'Staff Member'
        verbose_name_plural = 'Staff Members'
        indexes = [
            models.Index(fields=['staff_id']),
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['branch']),
        ]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        branch_info = f" - {self.branch}" if self.branch else ""
        return f"{self.full_name} ({self.staff_id}){branch_info}"


class Asset(models.Model):
    ASSET_TYPE_CHOICES = [
        ('vehicle', 'Vehicle'),
        ('equipment', 'Equipment'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('pending_certification', 'Pending Certification'),
        ('inactive', 'Inactive'),
        ('damaged', 'Damaged'),
    ]

    name = models.CharField(max_length=200, help_text='Asset display name')
    asset_type = models.CharField(max_length=50, choices=ASSET_TYPE_CHOICES, default='other')
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='active')
    assigned_staff = models.ForeignKey(
        'StaffMember',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assets',
        help_text='Staff assigned to this asset'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['asset_type', 'name']
        verbose_name = 'Asset'
        verbose_name_plural = 'Assets'

    def __str__(self):
        return f"{self.name} ({self.get_asset_type_display()})"

    def get_active_assignment(self):
        return self.assignments.filter(released_at__isnull=True).order_by('-assigned_at').first()

    def get_linked_assets(self):
        return Asset.objects.filter(
            models.Q(outgoing_asset_relationships__to_asset=self) |
            models.Q(incoming_asset_relationships__from_asset=self)
        ).distinct()

    def save(self, *args, **kwargs):
        old_assigned_staff = None
        if self.pk:
            old = Asset.objects.filter(pk=self.pk).first()
            if old:
                old_assigned_staff = old.assigned_staff

        super().save(*args, **kwargs)

        if old_assigned_staff != self.assigned_staff:
            if old_assigned_staff:
                self.assignments.filter(released_at__isnull=True).update(released_at=timezone.now())
            if self.assigned_staff:
                AssetAssignmentHistory.objects.create(
                    asset=self,
                    staff_member=self.assigned_staff,
                    branch=self.assigned_staff.branch if self.assigned_staff else None,
                )


class AssetRelationship(models.Model):
    RELATION_TYPE_CHOICES = [
        ('related', 'Related'),
        ('attached_to', 'Attached To'),
        ('supports', 'Supports'),
        ('document_for', 'Document For'),
        ('sub_asset', 'Sub Asset'),
    ]

    from_asset = models.ForeignKey(
        'Asset',
        on_delete=models.CASCADE,
        related_name='outgoing_asset_relationships'
    )
    to_asset = models.ForeignKey(
        'Asset',
        on_delete=models.CASCADE,
        related_name='incoming_asset_relationships'
    )
    relation_type = models.CharField(max_length=50, choices=RELATION_TYPE_CHOICES, default='related')
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_asset_relationships'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('from_asset', 'to_asset', 'relation_type')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['relation_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.from_asset} {self.get_relation_type_display()} {self.to_asset}"


class AssetAssignmentHistory(models.Model):
    asset = models.ForeignKey(
        'Asset',
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    staff_member = models.ForeignKey(
        'StaffMember',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignment_history'
    )
    branch = models.CharField(max_length=100, blank=True, null=True, help_text='Branch where the asset is assigned')
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_assets'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-assigned_at']
        indexes = [
            models.Index(fields=['asset']),
            models.Index(fields=['staff_member']),
            models.Index(fields=['assigned_at']),
        ]

    @property
    def is_active(self):
        return self.released_at is None

    def __str__(self):
        staff = str(self.staff_member) if self.staff_member else 'Unassigned'
        return f"{self.asset} → {staff} ({self.assigned_at.date()})"


# ========================
# Audit Log for tracking user actions
# ========================
class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'Created'),
        ('update', 'Updated'),
        ('delete', 'Deleted'),
        ('view', 'Viewed'),
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('permission_denied', 'Permission Denied'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['user', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.user} - {self.action} on {self.model_name} ({self.timestamp})"


# ========================
# Email Recipients Management
# ========================
class EmailRecipient(models.Model):
    """Store email addresses for expiry alert notifications"""
    email = models.EmailField(unique=True, max_length=254)
    full_name = models.CharField(max_length=100, blank=True, null=True, help_text='Optional: Full name of the recipient')
    is_active = models.BooleanField(default=True, help_text='Uncheck to temporarily disable this recipient')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_email_recipients')
    
    class Meta:
        ordering = ['email']
        verbose_name = 'Email Recipient'
        verbose_name_plural = 'Email Recipients'
    
    def __str__(self):
        if self.full_name:
            return f"{self.full_name} ({self.email})"
        return self.email


class EmailDeliveryLog(models.Model):
    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('queued', 'Queued'),
    ]

    recipient = models.ForeignKey(
        EmailRecipient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='delivery_logs'
    )
    recipient_email = models.EmailField(max_length=254)
    subject = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    message = models.TextField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['recipient_email', 'status']),
        ]

    def __str__(self):
        return f"{self.recipient_email} - {self.subject} ({self.status})"


# ========================
# Equipment Transfer/Handover Record
# ========================
class EquipmentTransfer(models.Model):
    """Track equipment handovers between staff members"""
    equipment = models.ForeignKey(
        OfficeEquipment,
        on_delete=models.CASCADE,
        related_name='transfers'
    )
    
    # Previous (from) user
    transferred_from = models.CharField(
        max_length=100,
        help_text='Name of the staff member who previously had this equipment'
    )
    transferred_from_department = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Department of the previous user'
    )
    transferred_from_email = models.EmailField(
        blank=True,
        null=True,
        help_text='Email of the previous user'
    )
    
    # New (to) user
    transferred_to = models.CharField(
        max_length=100,
        help_text='Name of the staff member receiving this equipment'
    )
    transferred_to_department = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Department of the new user'
    )
    transferred_to_email = models.EmailField(
        blank=True,
        null=True,
        help_text='Email of the new user'
    )
    
    # Transfer details
    transfer_date = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Reason for the transfer (e.g., "Staff reassignment", "Replacement")'
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text='Additional notes about the transfer'
    )
    
    # Recorded by
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='equipment_transfers_recorded'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-transfer_date']
        verbose_name = 'Equipment Transfer'
        verbose_name_plural = 'Equipment Transfers'
        indexes = [
            models.Index(fields=['-transfer_date']),
            models.Index(fields=['equipment', '-transfer_date']),
        ]
    
    def __str__(self):
        return f"{self.equipment.name}: {self.transferred_from} → {self.transferred_to} ({self.transfer_date.date()})"


# ========================
# Email Schedule Configuration
# ========================
class EmailSchedule(models.Model):
    """Global configuration for scheduled email alerts"""
    schedule_time = models.TimeField(
        default='10:00',
        help_text='Time of day to send expiry alert emails (HH:MM format)'
    )
    alert_days = models.PositiveIntegerField(
        default=15,
        help_text='Number of days in advance to check for expiring items'
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text='Enable/disable automatic email scheduling'
    )
    last_sent = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text='Last time emails were sent'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_email_schedules'
    )
    
    class Meta:
        verbose_name = 'Email Schedule'
        verbose_name_plural = 'Email Schedule'
    
    def __str__(self):
        status = "Enabled" if self.is_enabled else "Disabled"
        return f"Email Schedule ({self.schedule_time}) - {status}"
    
    def save(self, *args, **kwargs):
        # Ensure only one EmailSchedule record exists
        if not self.pk and EmailSchedule.objects.exists():
            # Update existing instead of creating new
            existing = EmailSchedule.objects.first()
            self.pk = existing.pk
            self.created_at = existing.created_at
            self.updated_at = existing.updated_at
        super().save(*args, **kwargs)


# ========================
# Company Documents Management
# ========================
class CompanyDocument(models.Model):
    """Track company documents with expiry dates and send notifications"""
    
    DOCUMENT_TYPE_CHOICES = [
        ('business_license', 'Business License'),
        ('insurance', 'Insurance Certificate'),
        ('permit', 'Permit'),
        ('certification', 'Certification'),
        ('contract', 'Contract'),
        ('agreement', 'Agreement'),
        ('registration', 'Registration'),
        ('tax', 'Tax Certificate'),
        ('compliance', 'Compliance Document'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('pending_renewal', 'Pending Renewal'),
        ('renewed', 'Renewed'),
    ]
    
    # Basic info
    name = models.CharField(max_length=200, help_text='Document name or title')
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPE_CHOICES, default='other')
    description = models.TextField(blank=True, null=True, help_text='Additional details about the document')
    
    # Issuing and expiry information
    issuing_authority = models.CharField(max_length=200, blank=True, null=True, help_text='Authority that issued the document')
    issue_date = models.DateField(blank=True, null=True)
    expiry_date = models.DateField(help_text='When the document expires')
    renewal_date = models.DateField(blank=True, null=True, help_text='Target date for renewal')
    
    # Status and tracking
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='active')
    document_number = models.CharField(max_length=100, blank=True, null=True, help_text='Document or certificate number')
    related_vehicle = models.ForeignKey(
        'CompanyAsset',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='company_documents',
        help_text='Optional company asset this document applies to'
    )
    related_equipment = models.ForeignKey(
        'OfficeEquipment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='company_documents',
        help_text='Optional equipment this document applies to'
    )
    related_asset = models.ForeignKey(
        'Asset',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='company_documents',
        help_text='Optional shared asset that this document applies to'
    )
    
    # Notification
    notify_days_before = models.PositiveIntegerField(
        default=30,
        help_text='Number of days before expiry to send notification'
    )
    
    # Optional fields
    location = models.CharField(max_length=200, blank=True, null=True, help_text='Where the document is stored')
    responsible_person = models.CharField(max_length=100, blank=True, null=True, help_text='Person responsible for renewal')
    responsible_staff = models.ForeignKey(
        'StaffMember',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents',
        help_text='Select an existing staff member responsible for this document'
    )
    notes = models.TextField(blank=True, null=True)

    @property
    def responsible_display(self):
        if self.responsible_staff:
            return str(self.responsible_staff)
        return self.responsible_person or 'Unassigned'
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_documents')
    
    class Meta:
        ordering = ['expiry_date']
        verbose_name = 'Company Document'
        verbose_name_plural = 'Company Documents'
        indexes = [
            models.Index(fields=['expiry_date']),
            models.Index(fields=['status']),
            models.Index(fields=['document_type']),
        ]
    
    def __str__(self):
        return f"{self.name} (Expires: {self.expiry_date})"

    @property
    def asset(self):
        return self.related_asset or self.related_vehicle or self.related_equipment

    @property
    def asset_display(self):
        if self.related_asset:
            return str(self.related_asset)
        if self.related_vehicle:
            return f"{self.related_vehicle.name} ({self.related_vehicle.license_plate})"
        if self.related_equipment:
            return str(self.related_equipment)
        return 'Company-wide'

    def save(self, *args, **kwargs):
        if self.related_vehicle:
            if self.related_vehicle.asset:
                self.related_asset = self.related_vehicle.asset
            else:
                asset = Asset.objects.create(
                    name=f"{self.related_vehicle.name} ({self.related_vehicle.license_plate})",
                    asset_type='vehicle',
                    description=self.related_vehicle.get_asset_type_display(),
                    status=self.related_vehicle.status,
                    assigned_staff=self.related_vehicle.assigned_staff,
                )
                self.related_asset = asset
                self.related_vehicle.asset = asset
                self.related_vehicle.save(update_fields=['asset'])
        elif self.related_equipment:
            if self.related_equipment.asset:
                self.related_asset = self.related_equipment.asset
            else:
                asset = Asset.objects.create(
                    name=f"{self.related_equipment.name} ({self.related_equipment.equipment_type})",
                    asset_type='equipment',
                    description=self.related_equipment.description or self.related_equipment.get_equipment_type_display(),
                    status=self.related_equipment.status,
                    assigned_staff=self.related_equipment.assigned_staff,
                )
                self.related_asset = asset
                self.related_equipment.asset = asset
                self.related_equipment.save(update_fields=['asset'])
        super().save(*args, **kwargs)

    @property
    def asset_type(self):
        if self.related_asset:
            return self.related_asset.asset_type
        if self.related_vehicle:
            return 'vehicle'
        if self.related_equipment:
            return 'equipment'
        return None

    def get_status(self):
        """Calculate document expiry status based on expiry date and notification window."""
        today = timezone.now().date()
        if not self.expiry_date:
            return 'unknown'

        notify_window = self.notify_days_before if self.notify_days_before is not None else 30
        if self.expiry_date < today:
            return 'expired'
        elif self.expiry_date <= today + timezone.timedelta(days=notify_window):
            return 'expiring'
        return 'safe'

    @property
    def expiry_status(self):
        return self.get_status()

    def days_until_expiry(self):
        """Return number of days until expiry"""
        if not self.expiry_date:
            return None
        today = timezone.now().date()
        delta = self.expiry_date - today
        return delta.days