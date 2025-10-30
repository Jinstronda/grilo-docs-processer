"""
Filter Document AI response to extract only tableBlock elements
Preserves: blockId, pageSpan, tableBlock structure
"""

def extract_table_blocks_recursive(obj, parent_page_span=None):
    """Recursively extract all tableBlock elements from nested structure
    
    Args:
        obj: Dictionary or list to search
        parent_page_span: pageSpan from parent block if nested
        
    Returns:
        list: All found tableBlock objects with metadata
    """
    found_tables = []
    
    if isinstance(obj, dict):
        # Check if this block contains a tableBlock
        if 'tableBlock' in obj:
            # Extract the table with its metadata
            table_obj = {
                'blockId': obj.get('blockId', 'unknown'),
                'pageSpan': obj.get('pageSpan', parent_page_span),
                'tableBlock': obj['tableBlock']
            }
            found_tables.append(table_obj)
        
        # Recursively search in all nested structures
        page_span = obj.get('pageSpan', parent_page_span)
        for value in obj.values():
            found_tables.extend(extract_table_blocks_recursive(value, page_span))
            
    elif isinstance(obj, list):
        # Search in list items
        for item in obj:
            found_tables.extend(extract_table_blocks_recursive(item, parent_page_span))
    
    return found_tables

def filter_table_blocks(api_response):
    """Extract only blocks containing tableBlock from API response

    Args:
        api_response: Full API response dict (supports both formats)
            - Layout Parser: {documentLayout: {blocks: [...]}}
            - OCR Processor: {document: {documentLayout: {blocks: [...]}}}
            
        Note: Recursively searches for tableBlocks at any nesting level

    Returns:
        Filtered JSON with only table blocks
    """
    # Navigate to blocks array (handle both response formats)
    if 'documentLayout' in api_response:
        # Layout Parser format: direct documentLayout at root
        document_layout = api_response.get('documentLayout', {})
    else:
        # OCR/Form Parser format: nested under document
        document = api_response.get('document', {})
        document_layout = document.get('documentLayout', {})
    
    all_blocks = document_layout.get('blocks', [])

    # Recursively extract all tableBlocks (handles nested structures)
    filtered_blocks = extract_table_blocks_recursive(all_blocks)

    # Return in same structure as requested
    return {
        "documentLayout": {
            "blocks": filtered_blocks
        }
    }

def count_tables(filtered_response):
    """Count number of tables in filtered response

    Args:
        filtered_response: Result from filter_table_blocks()

    Returns:
        int: Number of tables
    """
    blocks = filtered_response.get('documentLayout', {}).get('blocks', [])
    return len(blocks)
