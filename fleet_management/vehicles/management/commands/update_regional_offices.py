"""
Management command to update equipment regional office classification.
Run with: python manage.py update_regional_offices
"""

from django.core.management.base import BaseCommand
from django.db.models import Count
from vehicles.models import OfficeEquipment


class Command(BaseCommand):
    help = 'Update equipment with regional office classification'

    def handle(self, *args, **options):
        all_equipment = OfficeEquipment.objects.all()
        updated_count = 0

        for equip in all_equipment:
            regional = self.guess_regional_office(equip)
            if equip.regional_office != regional:
                equip.regional_office = regional
                equip.save(update_fields=['regional_office'])
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(f'✅ Updated {updated_count} equipment items'))

        breakdown = OfficeEquipment.objects.values('regional_office').annotate(count=Count('id')).order_by('regional_office')
        self.stdout.write('\n📍 Equipment by Regional Office:')
        for item in breakdown:
            office = item['regional_office']
            count = item['count']
            self.stdout.write(f"  - Telnet {office}: {count} items")

        breakdown_sub = OfficeEquipment.objects.values('subsidiary').annotate(count=Count('id')).order_by('subsidiary')
        self.stdout.write('\n🏢 Equipment by Subsidiary:')
        for item in breakdown_sub:
            sub = item['subsidiary']
            count = item['count']
            self.stdout.write(f"  - {sub}: {count} items")

        for office in ['Lagos', 'Abuja', 'Port Harcourt']:
            active = OfficeEquipment.objects.filter(regional_office=office, status='active').count()
            damaged = OfficeEquipment.objects.filter(regional_office=office, status='damaged').count()
            other = OfficeEquipment.objects.filter(regional_office=office).exclude(status__in=['active', 'damaged']).count()
            total = active + damaged + other
            self.stdout.write(f"\n📊 Telnet {office}:")
            self.stdout.write(f"  - Total: {total} items")
            self.stdout.write(f"  - Active: {active}")
            self.stdout.write(f"  - Damaged: {damaged}")
            self.stdout.write(f"  - Other: {other}")

    def guess_regional_office(self, equip):
        search_text = ' '.join(
            str(part).strip() for part in [equip.location, equip.tag_number, equip.subsidiary] if part
        ).lower()

        if any(token in search_text for token in ['abuja', 'abj']):
            return 'Abuja'
        if any(token in search_text for token in ['port harcourt', 'phc', 'ph/']):
            return 'Port Harcourt'
        if any(token in search_text for token in ['lagos', 'head office', 'headquarters', 'hq', 'ikeja', 'alausa']):
            return 'Lagos'

        return 'Lagos'
