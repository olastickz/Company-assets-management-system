"""
Django management command to import Telnet Group assets from ODS file.
Run with: python manage.py import_telnet_assets
"""

import zipfile
import xml.etree.ElementTree as ET
from django.core.management.base import BaseCommand
from django.db.models import Count
from vehicles.models import OfficeEquipment
from datetime import date


class Command(BaseCommand):
    help = 'Import equipment assets from Telnet Group ODS file'

    def handle(self, *args, **options):
        # Use the ODS file from the project root (4 levels up from this command file)
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        ods_file = os.path.join(base_dir, 'TELNET GROUP ASSET LIST JUNE, 2025 (1)..ods')

        try:
            with zipfile.ZipFile(ods_file, 'r') as zip_ref:
                content_xml = zip_ref.read('content.xml').decode('utf-8')

            root = ET.fromstring(content_xml)
            ns = {
                'table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
                'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
            }

            equipment_rows = []
            sheet_summary = {}
            for table in root.findall('.//table:table', ns):
                sheet_name = table.get('{urn:oasis:names:tc:opendocument:xmlns:table:1.0}name') or ''
                sheet_label = sheet_name.upper().replace(' ', '').replace('-', '').replace('_', '')
                # Process TELNET, SOFTWORKS, and ITECO sheets
                if not any(sub in sheet_label for sub in ['TELNET', 'SOFTWORKS', 'ITECO']):
                    continue

                regional_office = self.get_regional_office_from_sheet_name(sheet_label)
                subsidiary = self.get_subsidiary_from_sheet_name(sheet_label)
                schema = self.get_sheet_schema(sheet_label)
                
                sheet_items = 0

                for row in table.findall('table:table-row', ns):
                    cells = []
                    for cell in row.findall('table:table-cell', ns):
                        repeat = int(cell.get('{urn:oasis:names:tc:opendocument:xmlns:table:1.0}number-columns-repeated', '1'))
                        text = ''.join((t.text or '') for t in cell.findall('text:p', ns)).strip()
                        cells.extend([text] * repeat)

                    item = self.parse_equipment_row(cells, schema)
                    if not item:
                        continue

                    # Set regional office and subsidiary based on sheet source (most reliable)
                    item['regional_office'] = regional_office
                    item['subsidiary'] = subsidiary
                    item['sheet_source'] = sheet_label  # For debugging
                    equipment_rows.append(item)
                    sheet_items += 1
                
                sheet_summary[sheet_label] = {'region': regional_office, 'items': sheet_items}

            if not equipment_rows:
                self.stdout.write(self.style.WARNING('[WARNING] No Telnet equipment rows were detected in the ODS file.'))
                return

            self.stdout.write('\nSheet breakdown:')
            for sheet, summary in sheet_summary.items():
                self.stdout.write(f"  - {sheet}: {summary['items']} items for {summary['region']}")

            # Track updates vs creates
            items_to_create = []
            updated_count = 0
            updated_serials = set()
            updated_tags = set()

            for item in equipment_rows:
                serial_number = item['serial_number']
                tag_number = item['tag_number']

                # Try to find existing by serial or tag (case-insensitive)
                existing = None
                if serial_number and serial_number.upper() not in ('N/A', 'NA'):
                    existing = OfficeEquipment.objects.filter(serial_number__iexact=serial_number).first()
                if not existing and tag_number and tag_number.upper() not in ('N/A', 'NA'):
                    existing = OfficeEquipment.objects.filter(tag_number__iexact=tag_number).first()

                if existing:
                    # Update regional_office, location, and cost if they differ
                    updated = False
                    if existing.regional_office != item['regional_office']:
                        existing.regional_office = item['regional_office']
                        updated = True
                    if item.get('location') and existing.location != item['location']:
                        existing.location = item['location']
                        updated = True
                    if item.get('cost') is not None and existing.cost != item['cost']:
                        existing.cost = item['cost']
                        updated = True
                    if updated:
                        existing.save()
                        updated_count += 1
                        if serial_number:
                            updated_serials.add(serial_number.upper())
                        if tag_number:
                            updated_tags.add(tag_number.upper())
                else:
                    items_to_create.append(item)

            self.stdout.write(self.style.SUCCESS(f'[OK] Found {len(items_to_create)} new items to create'))
            if updated_count > 0:
                self.stdout.write(self.style.WARNING(f'[UPDATE] Updated {updated_count} existing items with new regional/location data'))

            batch_size = 50
            total_created = 0
            for i in range(0, len(items_to_create), batch_size):
                batch = items_to_create[i:i + batch_size]
                to_create = []
                for item in batch:
                    purchase_year = self.parse_year(item['year_of_purchase'])
                    eq_type = self.get_equipment_type(item['name'], item['description'])
                    status = self.normalize_status(item['status'])

                    to_create.append(
                        OfficeEquipment(
                            name=item['name'],
                            equipment_type=eq_type,
                            subsidiary=item['subsidiary'],
                            regional_office=item['regional_office'],
                            location=item['location'] or item['regional_office'],
                            serial_number=item['serial_number'],
                            tag_number=item['tag_number'],
                            assigned_user=item.get('assigned_user'),
                            purchase_date=(date(purchase_year, 1, 1) if purchase_year else None),
                            quantity=item['quantity'],
                            cost=item.get('cost'),
                            remarks=item.get('remarks'),
                            status=status,
                        )
                    )

                created = OfficeEquipment.objects.bulk_create(to_create)
                total_created += len(created)
                self.stdout.write(f"  - Batch {i // batch_size + 1}: Created {len(created)} items")

            self.stdout.write(self.style.SUCCESS(f'\n[OK] Total assets created: {total_created}'))
            if updated_count > 0:
                self.stdout.write(self.style.SUCCESS(f'[OK] Total assets updated: {updated_count}'))

            subsidiary_breakdown = OfficeEquipment.objects.values('subsidiary').annotate(count=Count('id'))
            self.stdout.write('\nSubsidiary breakdown:')
            for sub in subsidiary_breakdown.order_by('subsidiary'):
                self.stdout.write(f"  - {sub['subsidiary']}: {sub['count']} items")

            equipment_type_breakdown = OfficeEquipment.objects.values('equipment_type').annotate(count=Count('id'))
            self.stdout.write('\nEquipment type breakdown:')
            for eq_type in equipment_type_breakdown.order_by('equipment_type'):
                self.stdout.write(f"  - {eq_type['equipment_type']}: {eq_type['count']} items")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'[ERROR] Error: {str(e)}'))
            import traceback
            traceback.print_exc()

    def get_sheet_schema(self, sheet_label):
        if 'ABUJA' in sheet_label:
            return {
                'name': 0,
                'detail': 1,
                'location': 2,
                'qty': 7,
                'serial': 9,
                'year': 3,
                'tag': None,  # Abuja doesn't have tag numbers
                'user': None,
                'status': 5,
                'cost': 8,  # Try total value column instead
                'remarks': None,
            }

        if 'PHC' in sheet_label:
            return {
                'name': 1,
                'detail': None,
                'location': 2,
                'qty': 3,
                'serial': 4,
                'year': 5,
                'tag': 6,
                'user': None,
                'status': 7,
                'remarks': None,
            }

        return {
            'name': 2,
            'detail': None,
            'location': 3,
            'qty': 4,
            'serial': 5,
            'year': 6,
            'tag': 7,
            'user': 8,
            'status': 9,
            'cost': 10,
            'remarks': 10,
        }

    def get_regional_office_from_sheet_name(self, sheet_label):
        if 'ABUJA' in sheet_label or 'ABJ' in sheet_label:
            return 'Abuja'
        if 'PHC' in sheet_label or 'PORTHARCOURT' in sheet_label or 'PRTHAR' in sheet_label:
            return 'Port Harcourt'
        return 'Lagos'

    def get_subsidiary_from_sheet_name(self, sheet_label):
        if 'TELNET' in sheet_label:
            return 'Telnet'
        if 'SOFTWORKS' in sheet_label:
            return 'Softworks'
        if 'ITECO' in sheet_label:
            return 'ITECO'
        return 'Other'

    def parse_equipment_row(self, cells, schema):
        name = self.get_cell(cells, schema['name'])
        if not name:
            return None

        detail_text = self.get_cell(cells, schema.get('detail'))
        description = detail_text if detail_text and detail_text.upper() not in ('N/A', 'NA') else ''
        location = self.get_cell(cells, schema.get('location')) or ''
        quantity = self.parse_quantity(self.get_cell(cells, schema.get('qty')))
        serial_number = self.clean_value(self.get_cell(cells, schema.get('serial')))
        tag_number = self.clean_value(self.get_cell(cells, schema.get('tag')))
        year_of_purchase = self.get_cell(cells, schema.get('year'))
        assigned_user = self.get_cell(cells, schema.get('user'))
        status = self.get_cell(cells, schema.get('status'))
        cost = self.parse_cost(self.get_cell(cells, schema.get('cost')))
        remarks = self.get_cell(cells, schema.get('remarks'))

        if self.is_header_row(name, description):
            return None

        # Accept row if it has EITHER a serial number OR a tag number
        # For Abuja, we allow serial-only items
        if not serial_number and not tag_number:
            return None

        return {
            'name': name,
            'description': description,
            'location': location,
            'quantity': quantity,
            'serial_number': serial_number,
            'tag_number': tag_number,
            'year_of_purchase': year_of_purchase,
            'assigned_user': assigned_user,
            'status': status or '',
            'cost': cost,
            'remarks': remarks or '',
        }

    def get_cell(self, cells, index):
        if index is None or index >= len(cells):
            return ''
        return cells[index].strip()

    def clean_value(self, value):
        if not value:
            return None
        normalized = value.strip()
        if not normalized or normalized.upper() in ('N/A', 'NA', 'NONE', 'NULL'):
            return None
        return normalized

    def parse_quantity(self, quantity_value):
        if not quantity_value:
            return 1
        quantity_value = quantity_value.strip()
        if quantity_value.isdigit():
            return int(quantity_value)
        try:
            return int(float(quantity_value))
        except (ValueError, TypeError):
            return 1

    def parse_year(self, year_value):
        if not year_value:
            return None
        if isinstance(year_value, int):
            return year_value
        year_text = year_value.strip()
        if year_text.isdigit():
            return int(year_text)
        if len(year_text) == 4 and year_text.isnumeric():
            return int(year_text)
        return None

    def parse_cost(self, cost_value):
        """Parse cost values, handling formats like 'N257,626' or '895,000'"""
        if not cost_value:
            return None
        cost_text = cost_value.strip()
        if not cost_text or cost_text.upper() in ('N/A', 'NA', 'NONE', 'NULL'):
            return None

        # Remove currency symbols and commas
        cost_text = cost_text.replace('N', '').replace(',', '').replace(' ', '')

        try:
            return float(cost_text)
        except (ValueError, TypeError):
            return None

    def is_header_row(self, name, description):
        content = ' '.join([name, description]).lower()
        header_terms = [
            'item description', 'description', 's/n', 'serial no', 'i.d number',
            'asset inventory', 'company:', 'audit start date', 'audit end date',
            'total inventory', 'good inventory', 'bad inventory', 'office equipment',
            'office furniture', 'total equipment', 'name of verification officer',
        ]
        return any(term in content for term in header_terms)

    def get_equipment_type(self, name, description):
        combined = f"{name} {description}".lower()
        if 'laptop' in combined:
            return 'laptop'
        if any(keyword in combined for keyword in ['computer', 'desktop', 'server', 'ubuntu', 'linux']):
            return 'computer'
        if 'printer' in combined:
            return 'printer'
        if 'scanner' in combined:
            return 'scanner'
        if 'copier' in combined or 'photocopy' in combined:
            return 'copier'
        if 'ac' in combined or 'air' in combined or 'conditioner' in combined:
            return 'ac'
        if 'generator' in combined:
            return 'generator'
        if any(keyword in combined for keyword in ['furniture', 'chair', 'table', 'desk', 'sofa', 'cabinet', 'shelf']):
            return 'furniture'
        return 'other'

    def normalize_status(self, status_value):
        if not status_value:
            return 'active'
        lowered = status_value.strip().lower()
        if lowered in ('bad', 'faulty', 'damaged', 'not in use'):
            return 'damaged'
        return 'active'
