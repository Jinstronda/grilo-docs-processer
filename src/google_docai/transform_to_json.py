"""
Transform filtered tableBlock structure to final JSON format
Converts: tableBlock → {"table_id": "...", "page": N, "rows": [...]}
"""
from parse_values import parse_value

def extract_text_from_blocks(blocks):
    """Extract text content from cell blocks

    Args:
        blocks: Array of block objects containing text

    Returns:
        str: Concatenated text from all blocks
    """
    if not blocks:
        return ""

    text_parts = []
    for block in blocks:
        # Handle different block types
        if 'textBlock' in block:
            text_block = block['textBlock']
            text = text_block.get('text', '')
            text_parts.append(text)
        elif 'text' in block:
            text_parts.append(block['text'])

    return " ".join(text_parts).strip()

def extract_headers(header_rows):
    """Extract column headers from headerRows

    Args:
        header_rows: Array of header row objects

    Returns:
        list: Header texts
    """
    headers = []

    if not header_rows:
        return headers

    # Usually only one header row, but handle multiple
    for row in header_rows:
        cells = row.get('cells', [])
        for cell in cells:
            blocks = cell.get('blocks', [])
            text = extract_text_from_blocks(blocks)
            headers.append(text if text else f"col_{len(headers)}")

    return headers

def transform_table_block(table_block_obj):
    """Transform single tableBlock to final JSON format

    Args:
        table_block_obj: Object with blockId, pageSpan, tableBlock

    Returns:
        dict: Transformed table in final format
    """
    block_id = table_block_obj.get('blockId', 'unknown')
    page_span = table_block_obj.get('pageSpan', {})
    page_start = page_span.get('pageStart', 1)

    table_block = table_block_obj.get('tableBlock', {})

    # Extract headers
    header_rows = table_block.get('headerRows', [])
    headers = extract_headers(header_rows)

    # Extract body rows
    body_rows = table_block.get('bodyRows', [])
    rows = []

    for row_data in body_rows:
        cells = row_data.get('cells', [])
        row_dict = {}

        for i, cell in enumerate(cells):
            blocks = cell.get('blocks', [])
            text = extract_text_from_blocks(blocks)
            parsed = parse_value(text)

            if i == 0:
                # First column is row_name
                row_dict['row_name'] = parsed
            else:
                # Other columns use header names
                col_name = headers[i] if i < len(headers) else f"col_{i}"
                row_dict[col_name] = parsed

        rows.append(row_dict)

    return {
        'table_id': block_id,
        'page': page_start,
        'rows': rows
    }

def transform_all_tables(filtered_response):
    """Transform all tableBlocks to final JSON format

    Args:
        filtered_response: Result from filter_tables.filter_table_blocks()

    Returns:
        list: Array of transformed tables
    """
    blocks = filtered_response.get('documentLayout', {}).get('blocks', [])
    transformed_tables = []

    for block in blocks:
        try:
            transformed = transform_table_block(block)
            transformed_tables.append(transformed)
        except Exception as e:
            print(f"Error transforming table {block.get('blockId')}: {e}")
            import traceback
            traceback.print_exc()

    return transformed_tables
