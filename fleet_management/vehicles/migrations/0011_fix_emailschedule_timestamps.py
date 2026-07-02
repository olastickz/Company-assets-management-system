# Generated migration to fix EmailSchedule created_at constraint

from django.db import migrations, models
from django.utils import timezone


def set_default_timestamps(apps, schema_editor):
    """Set default timestamps for any null created_at values"""
    EmailSchedule = apps.get_model('vehicles', 'EmailSchedule')
    now = timezone.now()
    for schedule in EmailSchedule.objects.filter(created_at__isnull=True):
        schedule.created_at = now
        schedule.save()


class Migration(migrations.Migration):

    dependencies = [
        ('vehicles', '0010_alter_emailschedule_alert_days_and_more'),
    ]

    operations = [
        migrations.RunPython(set_default_timestamps, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='emailschedule',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='emailschedule',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
