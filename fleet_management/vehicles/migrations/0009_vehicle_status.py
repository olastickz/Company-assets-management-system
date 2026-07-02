# Generated manually for adding status field to Vehicle model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vehicles', '0008_emailschedule_alert_days'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehicle',
            name='status',
            field=models.CharField(
                choices=[('active', 'Active'), ('pending_certification', 'Pending Certification'), ('inactive', 'Inactive')],
                default='active',
                max_length=50
            ),
        ),
    ]