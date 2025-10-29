"""
Filter Document AI response to extract only tableBlock elements
Preserves: blockId, pageSpan, tableBlock structure
"""

def filter_table_blocks(api_response):
    """Extract only blocks containing tableBlock from API response

    Args:
        api_response: Full API response dict with document.documentLayout.blocks

    Returns:
        Filtered JSON with only table blocks
    """
    # Navigate to blocks array
    document = api_response.get('document', {})
    document_layout = document.get('documentLayout', {})
    all_blocks = document_layout.get('blocks', [])

    # Filter to keep only tableBlock elements
    filtered_blocks = []

    for block in all_blocks:
        if 'tableBlock' in block:
            # Preserve exact structure: blockId, pageSpan, tableBlock
            filtered_block = {
                'blockId': block.get('blockId'),
                'pageSpan': block.get('pageSpan'),
                'tableBlock': block['tableBlock']
            }
            filtered_blocks.append(filtered_block)

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
