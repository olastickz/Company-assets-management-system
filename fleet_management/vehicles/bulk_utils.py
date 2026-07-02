"""
Advanced search and bulk import utilities with file parsing and validation.

Provides functions for:
- Parsing CSV, Excel, and Word documents
- Validating row data
- Converting between file formats
"""
import csv
import os
import re
import tempfile
import logging
from io import StringIO, TextIOWrapper
from datetime import datetime
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


def parse_bulk_upload_csv(file_obj):
    """Parse CSV file for bulk vehicle/equipment upload.
    
    Args:
        file_obj: File object or CSV string content
        
    Returns:
        tuple: (rows_list, error_string) - Either list of dict rows with None error, or None with error message
    """
    try:
        if hasattr(file_obj, 'read'):
            content = file_obj.read().decode('utf-8')
        else:
            content = file_obj
        
        reader = csv.DictReader(StringIO(content))
        rows = list(reader)
        
        if not rows:
            raise ValidationError("CSV file is empty or has no valid rows")
        
        return rows, None
    except UnicodeDecodeError:
        logger.error("File must be UTF-8 encoded CSV")
        return None, "File must be UTF-8 encoded CSV"
    except ValidationError as e:
        logger.error(f"CSV validation error: {e}")
        return None, str(e)
    except Exception as e:
        logger.error(f"Error parsing CSV: {e}")
        return None, f"Error parsing CSV: {str(e)}"


def parse_Excel_equipment(file_obj):
    """Parse Excel file for equipment import with proper resource cleanup.
    
    Args:
        file_obj: File upload object from request.FILES
        
    Returns:
        tuple: (rows_list, error_string) - Either rows list with None error, or None with error message
    """
    tmp_file = None
    try:
        from .file_converters import excel_to_csv_equipment, equipment_to_csv_string
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            tmp_file = tmp.name
            tmp.write(file_obj.read())
            tmp.flush()
            equipment_data = excel_to_csv_equipment(tmp_file)
        
        # Convert to CSV-like format
        csv_string = equipment_to_csv_string(equipment_data)
        return parse_bulk_upload_csv(csv_string)
    
    except ValueError as e:
        logger.error(f"Excel parsing error: {e}")
        return None, f"Error parsing Excel file: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in Excel parsing: {e}")
        return None, f"Error parsing Excel file: {str(e)}"
    finally:
        # Clean up temporary file
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
                logger.debug(f"Cleaned up temporary file: {tmp_file}")
            except OSError as e:
                logger.warning(f"Failed to clean up temp file {tmp_file}: {e}")


def parse_excel_vehicles(file_obj):
    """Parse Excel file for vehicle import with proper resource cleanup."""
    tmp_file = None
    try:
        from .file_converters import excel_to_csv_vehicles, vehicles_to_csv_string

        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            tmp_file = tmp.name
            tmp.write(file_obj.read())
            tmp.flush()
            vehicle_data = excel_to_csv_vehicles(tmp_file)

        csv_string = vehicles_to_csv_string(vehicle_data)
        return parse_bulk_upload_csv(csv_string)
    except ValueError as e:
        logger.error(f"Excel parsing error: {e}")
        return None, f"Error parsing Excel file: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in Excel parsing: {e}")
        return None, f"Error parsing Excel file: {str(e)}"
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
                logger.debug(f"Cleaned up temporary file: {tmp_file}")
            except OSError as e:
                logger.warning(f"Failed to clean up temp file {tmp_file}: {e}")


def parse_docx_vehicles(file_obj):
    """Parse Word document for vehicle import with proper resource cleanup.
    
    Args:
        file_obj: File upload object from request.FILES
        
    Returns:
        tuple: (rows_list, error_string) - Either rows list with None error, or None with error message
    """
    tmp_file = None
    try:
        from .file_converters import docx_to_csv_vehicles, vehicles_to_csv_string
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp:
            tmp_file = tmp.name
            tmp.write(file_obj.read())
            tmp.flush()
            vehicle_data = docx_to_csv_vehicles(tmp_file)
        
        # Convert to CSV-like format
        csv_string = vehicles_to_csv_string(vehicle_data)
        return parse_bulk_upload_csv(csv_string)
    
    except ValueError as e:
        logger.error(f"DOCX parsing error: {e}")
        return None, f"Error parsing Word document: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in DOCX parsing: {e}")
        return None, f"Error parsing Word document: {str(e)}"
    finally:
        # Clean up temporary file
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
                logger.debug(f"Cleaned up temporary file: {tmp_file}")
            except OSError as e:
                logger.warning(f"Failed to clean up temp file {tmp_file}: {e}")


def validate_vehicle_row(row):
    """Validate a single vehicle row for required and format-correct fields.
    
    Args:
        row (dict): Vehicle data from CSV row
        
    Returns:
        dict: Dictionary of errors, empty if valid {field: error_message}
    """
    errors = {}
    
    # Required fields
    if not row.get('name', '').strip():
        errors['name'] = 'Vehicle name is required'
    
    if not row.get('license_plate', '').strip():
        errors['license_plate'] = 'License plate is required'
    
    # Optional VIN validation
    vin = row.get('vin_number', '').strip()
    if vin:
        if not re.match(r'^[A-HJ-NPR-Z0-9]{17}$', vin.upper()):
            errors['vin_number'] = 'VIN must be 17 characters and may not contain I, O, or Q'

    # Optional date validation
    date_fields = ['insurance_expiry', 'roadworthy_expiry', 'license_expiry', 'hackney_permit']
    for field in date_fields:
        if row.get(field, '').strip():
            try:
                datetime.strptime(row[field].strip(), '%Y-%m-%d')
            except ValueError:
                errors[field] = f'{field} must be in YYYY-MM-DD format'
    
    return errors


def validate_equipment_row(row):
    """Validate a single equipment row for required and format-correct fields.
    
    Args:
        row (dict): Equipment data from CSV row
        
    Returns:
        dict: Dictionary of errors, empty if valid {field: error_message}
    """
    errors = {}
    
    # Required fields
    if not row.get('name', '').strip():
        errors['name'] = 'Equipment name is required'
    
    if not row.get('equipment_type', '').strip():
        errors['equipment_type'] = 'Equipment type is required'
    
    # Validate type
    valid_types = ['computer', 'printer', 'scanner', 'copier', 'ac', 'generator', 'furniture', 'other']
    equipment_type = row.get('equipment_type', '').strip().lower()
    if equipment_type and equipment_type not in valid_types:
        errors['equipment_type'] = f'Invalid type. Must be one of: {", ".join(valid_types)}'
    
    # Optional date validation
    date_fields = ['purchase_date', 'warranty_expiry']
    for field in date_fields:
        if row.get(field, '').strip():
            try:
                datetime.strptime(row[field].strip(), '%Y-%m-%d')
            except ValueError:
                errors[field] = f'{field} must be in YYYY-MM-DD format'
    
    return errors
