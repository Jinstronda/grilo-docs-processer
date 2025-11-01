import json
from pathlib import Path

EXTRACTIONS_DIR = Path(__file__).parent / "extractions"

# Get all JSON files > 5KB (likely valid extractions, not failed ones)
json_files = [f for f in EXTRACTIONS_DIR.glob("*.json") if f.stat().st_size > 5000]

print(f"Checking {min(15, len(json_files))} JSON files...")
print("=" * 80)

good = 0
template = 0
encoding = 0
no_data = 0
errors = 0

for json_file in sorted(json_files)[:15]:
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle nested structure (data.extracted_tables or direct extracted_tables)
        if 'data' in data and 'extracted_tables' in data['data']:
            tables = data['data']['extracted_tables']
        elif 'extracted_tables' in data:
            tables = data['extracted_tables']
        else:
            print(f"NO_STRUCTURE | {json_file.name[:60]}")
            errors += 1
            continue
        
        # Count rows
        total_rows = 0
        for table in tables:
            if isinstance(table, dict) and 'table_data' in table:
                td = table.get('table_data', [])
                if isinstance(td, list):
                    total_rows += len(td)
        
        # Check for template
        json_str = str(data)
        is_template = '<page_number>' in json_str or '"column1"' in json_str or '"value1"' in json_str
        
        # Check for encoding issues
        raw_text = json_file.read_text(encoding='utf-8')
        has_encoding = '\ufffd' in raw_text or '�' in json_str
        
        if is_template:
            print(f"TEMPLATE     | {len(tables):2} tables | {total_rows:4} rows | {json_file.name[:50]}")
            template += 1
        elif total_rows == 0:
            print(f"NO_DATA      | {len(tables):2} tables | {total_rows:4} rows | {json_file.name[:50]}")
            no_data += 1
        elif has_encoding:
            print(f"ENCODING_BAD | {len(tables):2} tables | {total_rows:4} rows | {json_file.name[:50]}")
            encoding += 1
        else:
            print(f"OK           | {len(tables):2} tables | {total_rows:4} rows | {json_file.name[:50]}")
            good += 1
            
    except Exception as e:
        print(f"PARSE_ERROR  | {json_file.name[:60]} | {str(e)[:30]}")
        errors += 1

print("=" * 80)
print(f"RESULTS:")
print(f"  Perfect quality: {good}")
print(f"  Encoding issues: {encoding}")
print(f"  No data (empty): {no_data}")
print(f"  Template data: {template}")
print(f"  Parse errors: {errors}")
print("=" * 80)

