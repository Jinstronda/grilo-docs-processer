"""
Value parsing utilities for European number formats
Handles: € 1.234,56 → 1234.56, 95,5% → 95.5, etc.
"""
import re

def parse_value(text):
    """Parse cell value handling European formats

    Args:
        text: Raw cell text

    Returns:
        Parsed value (float/int/str/None)
    """
    if not text or not isinstance(text, str):
        return None

    text = text.strip().replace('\n', ' ')

    # Empty cells
    if not text or text in ['-', 'N/A', 'n/a', '']:
        return None

    # Euro amounts: € 1.234,56 → 1234.56
    if '€' in text:
        try:
            cleaned = text.replace('€', '').replace(' ', '').replace('.', '').replace(',', '.')
            return float(cleaned)
        except:
            return text

    # Percentages: 95,5% → 95.5
    if '%' in text:
        try:
            cleaned = text.replace('%', '').replace(' ', '').replace(',', '.')
            return float(cleaned)
        except:
            return text

    # Numbers with dots as thousands: 1.234 → 1234
    if re.match(r'^[\d\s.]+$', text):
        try:
            return int(text.replace(' ', '').replace('.', ''))
        except:
            return text

    # Numbers with commas as decimals: 95,5 → 95.5
    if ',' in text and re.match(r'^[\d\s.,]+$', text):
        try:
            return float(text.replace(' ', '').replace(',', '.'))
        except:
            return text

    return text
