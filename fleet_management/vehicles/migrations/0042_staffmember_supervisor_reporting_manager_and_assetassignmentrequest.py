import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('vehicles', '0041_split_manager_role'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='staffmember',
            name='reporting_manager',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='direct_reports', to='vehicles.staffmember'),
        ),
        migrations.AddField(
            model_name='staffmember',
            name='supervisor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='supervised_staff', to='vehicles.staffmember'),
        ),
        migrations.CreateModel(
            name='AssetAssignmentRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('supervisor_approved_at', models.DateTimeField(blank=True, null=True)),
                ('reporting_manager_approved_at', models.DateTimeField(blank=True, null=True)),
                ('supervisor_approval_required', models.BooleanField(default=False)),
                ('reporting_manager_approval_required', models.BooleanField(default=False)),
                ('requires_superadmin_approval', models.BooleanField(default=False)),
                ('superadmin_approved_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('pending', 'Pending approval'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=20)),
                ('reason', models.CharField(blank=True, max_length=255)),
                ('notes', models.TextField(blank=True)),
                ('rejection_note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('asset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignment_requests', to='vehicles.asset')),
                ('previous_staff', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='outgoing_assignment_requests', to='vehicles.staffmember')),
                ('requested_staff', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='incoming_assignment_requests', to='vehicles.staffmember')),
                ('requested_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='asset_assignment_requests', to=settings.AUTH_USER_MODEL)),
                ('supervisor_approver', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='supervisor_asset_approvals', to=settings.AUTH_USER_MODEL)),
                ('supervisor_approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_supervisor_asset_assignments', to=settings.AUTH_USER_MODEL)),
                ('reporting_manager_approver', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='manager_asset_approvals', to=settings.AUTH_USER_MODEL)),
                ('reporting_manager_approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_manager_asset_assignments', to=settings.AUTH_USER_MODEL)),
                ('superadmin_approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_superadmin_asset_assignments', to=settings.AUTH_USER_MODEL)),
                ('rejected_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='rejected_asset_assignments', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]