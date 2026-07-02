from django.contrib import admin
from .models import Asset, AssetAssignmentHistory, AssetRelationship, CompanyAsset, MaintenanceItem, OfficeEquipment, OfficeEquipmentMaintenance, UserRole, StaffMember, AuditLog, EmailRecipient, EmailDeliveryLog, EmailSchedule, EquipmentTransfer, CompanyDocument
from django import forms
from django.utils.safestring import mark_safe
from django.utils.html import format_html


class TimeWithAMPMWidget(forms.TimeInput):
    """Custom time widget that replaces the time input with hour/minute/AMPM dropdowns"""

    def render(self, name, value, attrs=None, renderer=None):
        # Parse the current value
        hour = 9  # Default to 9 AM
        minute = 0
        ampm = 'AM'

        if value:
            try:
                if hasattr(value, 'hour'):
                    hour_24 = value.hour
                    minute = value.minute
                else:
                    # Parse string format like "04:38"
                    from datetime import datetime
                    if isinstance(value, str) and ':' in value:
                        parsed_time = datetime.strptime(value, '%H:%M').time()
                        hour_24 = parsed_time.hour
                        minute = parsed_time.minute
                    else:
                        # Default values
                        hour_24 = 9
                        minute = 0

                # Convert to 12-hour format
                if hour_24 == 0:
                    hour = 12
                    ampm = 'AM'
                elif hour_24 < 12:
                    hour = hour_24
                    ampm = 'AM'
                elif hour_24 == 12:
                    hour = 12
                    ampm = 'PM'
                else:
                    hour = hour_24 - 12
                    ampm = 'PM'
            except (ValueError, TypeError, AttributeError):
                # If parsing fails, use defaults
                hour = 9
                minute = 0
                ampm = 'AM'
        else:
            # No value provided, use defaults
            hour = 9
            minute = 0
            ampm = 'AM'

        # Create hour dropdown (1-12) - restrict to valid hours only
        hour_options = ''
        for i in range(1, 13):
            selected = 'selected' if i == hour else ''
            hour_options += f'<option value="{i}" {selected}>{i}</option>'

        # Create minute dropdown (00, 15, 30, 45 for simplicity) - restrict to valid time intervals
        valid_minutes = [0, 15, 30, 45]
        minute_options = ''
        for min_val in valid_minutes:
            selected = 'selected' if min_val == minute - (minute % 15) else ''  # Round to nearest 15
            minute_options += f'<option value="{min_val:02d}" {selected}>{min_val:02d}</option>'

        # Create AM/PM dropdown - restrict to AM/PM only
        am_selected = 'selected' if ampm == "AM" else ''
        pm_selected = 'selected' if ampm == "PM" else ''
        am_options = f'<option value="AM" {am_selected}>AM</option>'
        pm_options = f'<option value="PM" {pm_selected}>PM</option>'

        # Combine into HTML that replaces the time input
        # Add input validation attributes
        html = '''
        <div style="display: inline-flex; gap: 5px; align-items: center;">
            <select name="''' + str(name) + '''_hour" style="width: 60px;" required>
                ''' + hour_options + '''
            </select>
            <span>:</span>
            <select name="''' + str(name) + '''_minute" style="width: 60px;" required>
                ''' + minute_options + '''
            </select>
            <select name="''' + str(name) + '''_ampm" style="width: 60px;" required>
                ''' + am_options + '''
                ''' + pm_options + '''
            </select>
        </div>
        '''

        return mark_safe(html)


# Custom form for EmailSchedule with AM/PM time input
class EmailScheduleForm(forms.ModelForm):
    schedule_time = forms.TimeField(
        widget=TimeWithAMPMWidget(),
        help_text='Select hour, minute, and AM/PM to set the daily email schedule time.'
    )

    class Meta:
        model = EmailSchedule
        fields = '__all__'
        exclude = ['created_at', 'updated_at']  # These are auto-generated

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set initial values for the widget
        if self.instance and self.instance.pk and self.instance.schedule_time:
            time_obj = self.instance.schedule_time
            hour_24 = time_obj.hour
            minute = time_obj.minute

            # Convert to 12-hour format for widget
            if hour_24 == 0:
                hour = 12
                ampm = 'AM'
            elif hour_24 < 12:
                hour = hour_24
                ampm = 'AM'
            elif hour_24 == 12:
                hour = 12
                ampm = 'PM'
            else:
                hour = hour_24 - 12
                ampm = 'PM'

            # Set initial data for the widget fields
            self.initial[f'schedule_time_hour'] = hour
            self.initial[f'schedule_time_minute'] = f"{minute:02d}"
            self.initial[f'schedule_time_ampm'] = ampm
        else:
            # For new instances, set default values
            self.initial[f'schedule_time_hour'] = 9
            self.initial[f'schedule_time_minute'] = '00'
            self.initial[f'schedule_time_ampm'] = 'AM'

    def clean_schedule_time(self):
        """Convert the separate hour/minute/ampm fields back to a Time object with validation"""
        hour = self.data.get(f'schedule_time_hour')
        minute = self.data.get(f'schedule_time_minute')
        ampm = self.data.get(f'schedule_time_ampm')

        # Validate that all required fields are provided
        if not hour or not minute or not ampm:
            raise forms.ValidationError("Please select hour, minute, and AM/PM.")

        # Validate hour range (1-12)
        try:
            hour = int(hour)
            if not 1 <= hour <= 12:
                raise forms.ValidationError("Hour must be between 1 and 12.")
        except ValueError:
            raise forms.ValidationError("Invalid hour value.")

        # Validate minute values (only allow 00, 15, 30, 45)
        try:
            minute = int(minute)
            if minute not in [0, 15, 30, 45]:
                raise forms.ValidationError("Minute must be 00, 15, 30, or 45.")
        except ValueError:
            raise forms.ValidationError("Invalid minute value.")

        # Validate AM/PM
        if ampm not in ['AM', 'PM']:
            raise forms.ValidationError("AM/PM must be either AM or PM.")

        # Convert 12-hour to 24-hour
        if ampm == 'AM':
            if hour == 12:
                hour_24 = 0
            else:
                hour_24 = hour
        else:  # PM
            if hour == 12:
                hour_24 = 12
            else:
                hour_24 = hour + 12

        from datetime import time
        return time(hour_24, minute)


@admin.register(EmailSchedule)
class EmailScheduleAdmin(admin.ModelAdmin):
    form = EmailScheduleForm
    list_display = ('get_schedule_display', 'get_alert_days_display', 'get_enabled_badge', 'last_sent')
    list_filter = ('is_enabled', 'updated_at')
    readonly_fields = ('last_sent', 'created_at', 'updated_at', 'updated_by')
    fieldsets = (
        ('⏰ Email Schedule Configuration', {
            'fields': ('schedule_time', 'alert_days', 'is_enabled'),
            'description': 'Set the time to send daily expiry alert emails using the hour, minute, and AM/PM dropdowns.'
        }),
        ('📊 Status', {
            'fields': ('last_sent',),
        }),
        ('📝 Metadata', {
            'fields': ('created_at', 'updated_at', 'updated_by'),
            'classes': ('collapse',)
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Set default time for new objects
        if obj is None:  # This is an "Add" form
            from datetime import time
            form.base_fields['schedule_time'].initial = time(10, 0)  # 10:00 AM default
        return form
    
    def get_schedule_display(self, obj):
        """Display schedule time in a readable 12-hour format"""
        # Show schedule with AM/PM for clarity
        return f"Daily at {obj.schedule_time.strftime('%I:%M %p').lstrip('0')}"
    get_schedule_display.short_description = "Schedule"
    
    def get_alert_days_display(self, obj):
        """Display alert days in a readable format"""
        return f"{obj.alert_days} days"
    get_alert_days_display.short_description = "Alert Window"
    
    def get_enabled_badge(self, obj):
        """Show enabled/disabled status with colors"""
        if obj.is_enabled:
            return '✅ Enabled'
        return '❌ Disabled'
    get_enabled_badge.short_description = "Status"
    
    def save_model(self, request, obj, form, change):
        """Set the updated_by field before saving"""
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
    
    def has_add_permission(self, request):
        """Only allow adding if there are no existing schedules (should only be one)"""
        # Check if an EmailSchedule already exists
        if EmailSchedule.objects.exists() and not request.user.is_superuser:
            return False
        # Limit to one record for superusers too
        return True
    
    def has_delete_permission(self, request, obj=None):
        """Only superusers can delete the schedule"""
        return request.user.is_superuser
    
    def has_change_permission(self, request, obj=None):
        """Only superusers can modify schedule"""
        return request.user.is_superuser
    
    def has_view_permission(self, request, obj=None):
        """All users can view schedule"""
        return True


@admin.register(CompanyAsset)
class CompanyAssetAdmin(admin.ModelAdmin):
    list_display = ('name', 'make', 'model', 'license_plate', 'vin_number', 'asset_type', 'status', 'get_status_display')
    list_filter = ('asset_type', 'status', 'created_at')
    search_fields = ('name', 'make', 'model', 'license_plate', 'vin_number')
    readonly_fields = ('created_at', 'updated_at')

    def get_status_display(self, obj):
        """Display status with color coding"""
        status_colors = {
            'active': 'green',
            'pending_certification': 'orange',
            'inactive': 'red',
        }
        color = status_colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_status_display()
        )
    get_status_display.short_description = 'Status'

admin.site.register(MaintenanceItem)

@admin.register(OfficeEquipment)
class OfficeEquipmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'equipment_type', 'assigned_to_display', 'status', 'subsidiary', 'regional_office', 'warranty_expiry', 'get_status_display')
    list_filter = ('equipment_type', 'status', 'subsidiary', 'regional_office', 'created_at')
    search_fields = ('name', 'serial_number', 'tag_number', 'assigned_user', 'assigned_staff__staff_id', 'assigned_staff__first_name', 'assigned_staff__last_name')
    readonly_fields = ('created_at', 'updated_at')

    def get_status_display(self, obj):
        """Display status with color coding"""
        status_colors = {
            'active': 'green',
            'pending_certification': 'orange',
            'inactive': 'red',
            'damaged': 'red',
        }
        color = status_colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_status_display()
        )
    get_status_display.short_description = 'Status'

admin.site.register(OfficeEquipmentMaintenance)


# ===============================
# Equipment Transfer Admin
# ===============================
@admin.register(EquipmentTransfer)
class EquipmentTransferAdmin(admin.ModelAdmin):
    list_display = ['get_equipment_name', 'transferred_from', 'transferred_to', 'transfer_date', 'reason', 'recorded_by']
    list_filter = ['transfer_date', 'equipment__subsidiary']
    search_fields = ['equipment__name', 'transferred_from', 'transferred_to', 'reason']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Equipment', {
            'fields': ('equipment',)
        }),
        ('Transfer Details', {
            'fields': ('transfer_date', 'reason', 'notes')
        }),
        ('From (Previous User)', {
            'fields': ('transferred_from', 'transferred_from_department', 'transferred_from_email'),
            'classes': ('collapse',)
        }),
        ('To (New User)', {
            'fields': ('transferred_to', 'transferred_to_department', 'transferred_to_email')
        }),
        ('Record Information', {
            'fields': ('recorded_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_equipment_name(self, obj):
        return obj.equipment.name
    get_equipment_name.short_description = 'Equipment'
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)


# ===============================
# Custom Admin Views for Email System
# ===============================
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.urls import path


class EmailAdminSite(admin.AdminSite):
    site_header = "Assets Management Administration"
    site_title = "Assets Admin"
    index_title = "Assets Management System"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('email-system/', self.admin_view(self.email_system_view), name='email_system'),
        ]
        return custom_urls + urls

    def email_system_view(self, request):
        """Custom admin view for email system management"""
        from vehicles.email_notifications import send_expiry_alerts
        from vehicles.models import EmailSchedule, EmailRecipient
        from vehicles.apps import scheduler

        context = self.each_context(request)
        context.update({
            'title': 'Email System Management',
        })

        if request.method == 'POST':
            action = request.POST.get('action')

            if action == 'trigger':
                result = send_expiry_alerts()
                if result['status'] == 'sent':
                    messages.success(request, f"Email sent to {len(result.get('recipients', []))} recipients")
                elif result['status'] == 'no_alerts':
                    messages.info(request, "No expiring items found")
                else:
                    messages.error(request, f"Failed to send email: {result.get('message', 'Unknown error')}")

            elif action == 'restart_scheduler':
                if scheduler:
                    scheduler.shutdown(wait=True)
                    from vehicles.apps import VehiclesConfig
                    config = VehiclesConfig('vehicles', None)
                    config.setup_scheduler()
                    messages.success(request, "Scheduler restarted")
                else:
                    messages.error(request, "Scheduler not available")

            return redirect('admin:email_system')

        # Get current status
        schedule = EmailSchedule.objects.first()
        recipients = EmailRecipient.objects.filter(is_active=True)

        from vehicles.email_notifications import get_expiring_vehicles, get_expiring_equipment
        expiring_vehicles = get_expiring_vehicles()
        expiring_equipment = get_expiring_equipment()

        context.update({
            'schedule': schedule,
            'recipients': recipients,
            'expiring_vehicles': expiring_vehicles,
            'expiring_equipment': expiring_equipment,
            'scheduler_running': scheduler and scheduler.running if scheduler else False,
            'total_expiring': len(expiring_vehicles) + len(expiring_equipment),
        })

        return render(request, 'admin/email_system.html', context)


# Replace default admin site with custom one
admin.site = EmailAdminSite()
admin.site.register(UserRole)
admin.site.register(StaffMember)
admin.site.register(AuditLog)
admin.site.register(EmailRecipient)
admin.site.register(EmailDeliveryLog)
admin.site.register(EmailSchedule)

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('name', 'asset_type', 'status', 'assigned_staff', 'created_at')
    list_filter = ('asset_type', 'status')
    search_fields = ('name', 'description', 'assigned_staff__staff_id', 'assigned_staff__first_name', 'assigned_staff__last_name')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(AssetAssignmentHistory)
class AssetAssignmentHistoryAdmin(admin.ModelAdmin):
    list_display = ('asset', 'staff_member', 'branch', 'assigned_at', 'released_at')
    list_filter = ('branch', 'assigned_at', 'released_at')
    search_fields = ('asset__name', 'staff_member__staff_id', 'staff_member__first_name', 'staff_member__last_name')
    readonly_fields = ('assigned_at',)

@admin.register(AssetRelationship)
class AssetRelationshipAdmin(admin.ModelAdmin):
    list_display = ('from_asset', 'relation_type', 'to_asset', 'created_at')
    list_filter = ('relation_type', 'created_at')
    search_fields = ('from_asset__name', 'to_asset__name', 'notes')
    readonly_fields = ('created_at',)

# Register Django's built-in User and Group models
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.forms import PasswordInput
from django.utils.safestring import mark_safe

class PasswordInputWithToggle(PasswordInput):
    """Custom password input with eye icon toggle for visibility"""
    
    def render(self, name, value, attrs=None, renderer=None):
        # Don't display stored password hash
        value = None
        
        # Get the default rendered input
        html = super().render(name, value, attrs, renderer)
        
        # Add eye icon toggle functionality
        field_id = attrs.get('id', f'id_{name}') if attrs else f'id_{name}'
        toggle_id = f'{field_id}_toggle'
        
        # Wrap with custom HTML for eye icon
        custom_html = f'''
        <div style="position: relative; display: inline-block; width: 100%;">
            {html}
            <button type="button" id="{toggle_id}" 
                    style="position: absolute; right: 10px; top: 50%; transform: translateY(-50%); 
                           background: none; border: none; cursor: pointer; font-size: 18px; padding: 0;"
                    onclick="togglePasswordVisibility('{field_id}', '{toggle_id}')"
                    tabindex="-1">
                👁️
            </button>
        </div>
        <style>
            #{toggle_id}:hover {{
                opacity: 0.7;
            }}
            #{field_id} {{
                padding-right: 40px;
            }}
        </style>
        <script>
            function togglePasswordVisibility(fieldId, toggleId) {{
                const field = document.getElementById(fieldId);
                const toggle = document.getElementById(toggleId);
                
                if (field.type === 'password') {{
                    field.type = 'text';
                    toggle.textContent = '🙈';
                }} else {{
                    field.type = 'password';
                    toggle.textContent = '👁️';
                }}
            }}
        </script>
        '''
        
        return mark_safe(custom_html)

class UserAdmin(BaseUserAdmin):
    """Custom UserAdmin with organized fieldsets for add user form"""
    fieldsets = (
        ('👤 User Information', {
            'fields': ('username', 'password'),
            'description': 'Basic user credentials'
        }),
        ('📋 Personal Information', {
            'fields': ('first_name', 'last_name', 'email'),
            'description': 'User personal details'
        }),
        ('🔐 Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'description': 'User access and permission settings'
        }),
        ('📅 Important Dates', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',),
            'description': 'Account creation and login timestamps'
        }),
    )
    
    add_fieldsets = (
        ('👤 Create User', {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'first_name', 'last_name', 'email'),
            'description': 'Enter the basic information to create a new user account'
        }),
        ('🔐 Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups'),
            'description': 'Set user permissions and access levels'
        }),
    )
    
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'date_joined')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('username',)
    filter_horizontal = ('groups', 'user_permissions')
    
    def get_form(self, request, obj=None, **kwargs):
        """Override form to add custom password widget with visibility toggle"""
        form = super().get_form(request, obj, **kwargs)
        
        # Apply custom widget to password fields in add form
        if obj is None:  # This is an "Add" form
            if 'password1' in form.base_fields:
                form.base_fields['password1'].widget = PasswordInputWithToggle()
            if 'password2' in form.base_fields:
                form.base_fields['password2'].widget = PasswordInputWithToggle()
        
        return form

admin.site.register(User, UserAdmin)
admin.site.register(Group)


# ===============================
# Company Documents Admin
# ===============================
@admin.register(CompanyDocument)
class CompanyDocumentAdmin(admin.ModelAdmin):
    list_display = ['name', 'document_type', 'expiry_date', 'get_status_display', 'responsible_display']
    list_filter = ['document_type', 'status', 'expiry_date']
    search_fields = ['name', 'document_number', 'responsible_person', 'responsible_staff__staff_id', 'responsible_staff__first_name', 'responsible_staff__last_name', 'issuing_authority', 'related_asset__name', 'related_asset__asset_type', 'related_company_asset__name', 'related_company_asset__license_plate', 'related_equipment__name', 'related_equipment__serial_number']
    readonly_fields = ['created_at', 'updated_at', 'get_days_until_expiry']
    
    fieldsets = (
        ('📄 Document Information', {
            'fields': ('name', 'document_type', 'description', 'related_asset', 'related_vehicle', 'related_equipment')
        }),
        ('📅 Dates', {
            'fields': ('issue_date', 'expiry_date', 'renewal_date', 'get_days_until_expiry')
        }),
        ('⚙️ Details', {
            'fields': ('document_number', 'issuing_authority', 'status')
        }),
        ('🔔 Notifications', {
            'fields': ('notify_days_before',),
            'description': 'Alert will be sent this many days before expiry'
        }),
        ('👤 Management', {
            'fields': ('responsible_person', 'location', 'notes'),
            'classes': ('collapse',)
        }),
        ('📊 Tracking', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )
    
    def get_status_display(self, obj):
        status = obj.get_status()
        if status == 'expired':
            color = '#d32f2f'  # Red
            icon = '❌'
        elif status == 'expiring':
            color = '#f57c00'  # Orange
            icon = '⚠️'
        else:
            color = '#388e3c'  # Green
            icon = '✅'
        
        return format_html(
            '<span style="color: {};">{} {}</span>',
            color,
            icon,
            status.title()
        )
    get_status_display.short_description = 'Status'
    
    def get_days_until_expiry(self, obj):
        days = obj.days_until_expiry()
        if days < 0:
            return format_html('<span style="color: #d32f2f;"><strong>EXPIRED {} days ago</strong></span>', abs(days))
        elif days <= obj.notify_days_before:
            return format_html('<span style="color: #f57c00;"><strong>{} days remaining</strong></span>', days)
        else:
            return format_html('<span style="color: #388e3c;">{} days remaining</span>', days)
    get_days_until_expiry.short_description = 'Days Until Expiry'
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)