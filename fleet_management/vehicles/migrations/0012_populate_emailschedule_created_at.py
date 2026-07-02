# This migration is no longer needed - use 0011_fix_emailschedule_timestamps instead

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('vehicles', '0011_fix_emailschedule_timestamps'),
    ]

    operations = [
        # No operations - the fix is handled in 0011
    ]
