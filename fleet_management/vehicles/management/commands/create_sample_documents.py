from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from vehicles.models import CompanyDocument, CompanyAsset
import random


class Command(BaseCommand):
    help = 'Create sample company documents for vehicles'

    def handle(self, *args, **options):
        vehicles = CompanyAsset.objects.filter(asset_type__in=['car', 'van', 'truck', 'bus', 'motorbike'])
        
        if not vehicles.exists():
            self.stdout.write(self.style.ERROR('No vehicles found in the database.'))
            return

        doc_types = [
            ('insurance', 'Insurance Certificate'),
            ('permit', 'Vehicle Permit'),
            ('registration', 'Vehicle Registration'),
            ('compliance', 'Compliance Document'),
        ]
        
        authorities = ['FRSC', 'Ministry of Transport', 'Vehicle Inspection Authority', 'Insurance Board']
        locations = ['Office Safe', 'Vehicle Glove Box', 'Manager Office', 'Compliance Folder']
        
        created_count = 0
        today = timezone.now().date()

        for vehicle in vehicles:
            # Create 1-3 documents per vehicle
            num_docs = random.randint(1, 3)
            for _ in range(num_docs):
                doc_type, doc_type_display = random.choice(doc_types)
                
                # Vary expiry dates
                days_offset = random.randint(0, 365)
                expiry_date = today + timedelta(days=days_offset)
                issue_date = today - timedelta(days=365)
                
                doc = CompanyDocument(
                    name=f"{vehicle.name} - {doc_type_display}",
                    document_type=doc_type,
                    description=f"Document for {vehicle.name} ({vehicle.license_plate})",
                    issuing_authority=random.choice(authorities),
                    issue_date=issue_date,
                    expiry_date=expiry_date,
                    status='active',
                    document_number=f"{doc_type.upper()}-{vehicle.license_plate}-{today.year}",
                    related_vehicle=vehicle,
                    notify_days_before=30,
                    location=random.choice(locations),
                    notes=f"Sample document for testing. Automatically created.",
                )
                doc.save()
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully created {created_count} sample documents for {vehicles.count()} vehicles.'))
