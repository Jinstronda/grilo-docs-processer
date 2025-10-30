"""
API client for Google Document AI Layout Parser
Handles authentication and API calls
"""
import base64
import requests
import time
from google.auth.transport.requests import Request

# Document AI endpoint (Layout Parser)
ENDPOINT_URL = "https://eu-documentai.googleapis.com/v1/projects/988857320354/locations/eu/processors/92b16a912417ec56:process"

def call_layout_parser(pdf_path_or_gcs_uri, credentials, verbose=True, use_gcs=False):
    """Call Document AI Layout Parser API

    Args:
        pdf_path_or_gcs_uri: Path to local PDF file or GCS URI (gs://bucket/path)
        credentials: Google service account credentials
        verbose: Print progress
        use_gcs: If True, treat input as GCS URI instead of local file

    Returns:
        dict: API response JSON
    """
    try:
        if verbose:
            print(f"Calling Document AI Layout Parser...")

        # Get access token
        credentials.refresh(Request())
        access_token = credentials.token

        # Prepare request headers
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        # Prepare request body based on source
        if use_gcs:
            # Direct GCS URI - no download needed!
            if verbose:
                print(f"  Using GCS URI: {pdf_path_or_gcs_uri[:60]}...")
            
            body = {
                'gcsDocument': {
                    'gcsUri': pdf_path_or_gcs_uri,
                    'mimeType': 'application/pdf'
                }
            }
        else:
            # Local file - read and encode to base64
            with open(pdf_path_or_gcs_uri, 'rb') as f:
                pdf_content = f.read()

            if verbose:
                print(f"  PDF size: {len(pdf_content) / 1024:.2f} KB")

            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
            
            body = {
                'rawDocument': {
                    'content': pdf_base64,
                    'mimeType': 'application/pdf'
                }
            }

        if verbose:
            print(f"  Sending request to Document AI...")

        # Make API call with retry logic
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    ENDPOINT_URL,
                    headers=headers,
                    json=body,
                    timeout=120  # 2 minutes timeout
                )

                if response.status_code == 200:
                    if verbose:
                        print(f"  [OK] API call successful")

                    result = response.json()

                    # Count pages
                    document = result.get('document', {})
                    pages = document.get('pages', [])
                    if verbose:
                        print(f"  Processed {len(pages)} pages")

                    return result

                elif response.status_code == 429:
                    # Rate limit - retry with backoff
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)
                        if verbose:
                            print(f"  Rate limit hit, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise Exception(f"Rate limit exceeded after {max_retries} retries")

                else:
                    raise Exception(f"API error {response.status_code}: {response.text}")

            except requests.Timeout:
                if attempt < max_retries - 1:
                    if verbose:
                        print(f"  Timeout, retrying...")
                    time.sleep(retry_delay)
                    continue
                else:
                    raise Exception("Request timed out after retries")

        raise Exception("Failed after all retries")

    except Exception as e:
        print(f"  [ERROR] API error: {e}")
        import traceback
        traceback.print_exc()
        return None
