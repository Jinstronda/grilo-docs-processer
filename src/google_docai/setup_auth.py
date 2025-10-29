"""
Setup authentication for Google Document AI using user account
Run this once to authenticate as joao.panizzutti@augustalabs.ai
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/cloud-platform']

def setup_user_credentials():
    """Setup user credentials via OAuth flow"""

    print("="*80)
    print("Google Document AI - User Authentication Setup")
    print("="*80 + "\n")

    # Get OAuth credentials from .env
    client_id = os.getenv("DOCAI_OAUTH_CLIENT_ID")
    client_secret = os.getenv("DOCAI_OAUTH_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("✗ Error: DOCAI_OAUTH_CLIENT_ID and DOCAI_OAUTH_CLIENT_SECRET not found in .env")
        return

    # Create OAuth client configuration
    client_config = {
        "installed": {
            "client_id": client_id,
            "project_id": "988857320354",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": client_secret,
            "redirect_uris": ["http://localhost"]
        }
    }

    print("Authenticating...")
    print("-" * 80)
    print("A browser window will open.")
    print("Log in as: joao.panizzutti@augustalabs.ai\n")

    # Run OAuth flow
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    credentials = flow.run_local_server(port=0)

    # Save credentials
    creds_path = Path.home() / '.google_docai_credentials.json'
    with open(creds_path, 'w') as f:
        f.write(credentials.to_json())

    print(f"\n✓ Credentials saved to: {creds_path}")
    print("\nYou can now run test_single.py")

if __name__ == "__main__":
    setup_user_credentials()
