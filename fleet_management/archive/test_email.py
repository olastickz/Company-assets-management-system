from django.core.management.base import BaseCommand
from vehicles.scheduler import send_scheduled_expiry_alerts

class Command(BaseCommand):
    help = 'Manually trigger the scheduled expiry alerts email'

    def handle(self, *args, **options):
        self.stdout.write('🔔 Manually triggering expiry alerts...')
        result = send_scheduled_expiry_alerts()

        if result['status'] == 'sent':
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Email sent! {result['message']}\n"
                    f"🚗 Vehicles: {result['vehicles_count']}\n"
                    f"🖥️  Equipment: {result['equipment_count']}\n"
                    f"👥 Recipients: {', '.join(result['recipients'])}"
                )
            )
        elif result['status'] == 'no_alerts':
            self.stdout.write(
                self.style.WARNING(f"⚠️  {result['message']}")
            )
        elif result['status'] == 'no_recipients':
            self.stdout.write(
                self.style.ERROR(f"❌ {result['message']}")
            )
        elif result['status'] == 'no_schedule':
            self.stdout.write(
                self.style.ERROR(f"❌ {result['message']}")
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"❌ {result['message']}")
            )