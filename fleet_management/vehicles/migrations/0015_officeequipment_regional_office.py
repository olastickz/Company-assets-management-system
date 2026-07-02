from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vehicles', '0014_equipmenttransfer'),
    ]

    operations = [
        migrations.AddField(
            model_name='officeequipment',
            name='regional_office',
            field=models.CharField(
                choices=[('Lagos', 'Telnet Lagos'), ('Abuja', 'Telnet Abuja'), ('Port Harcourt', 'Telnet Port Harcourt')],
                default='Lagos',
                help_text='Main regional Telnet office',
                max_length=50
            ),
        ),
        migrations.AlterField(
            model_name='officeequipment',
            name='location',
            field=models.CharField(blank=True, help_text='Specific office/building/room location', max_length=100, null=True),
        ),
    ]
