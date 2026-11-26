"""Google sign-in (OAuth 2.0) for CloudPod.

Two files live in the 'credentials' folder, NEVER in the source code:
  credentials.json  - the OAuth client file you download from Google Cloud Console
  token.json        - created automatically after you sign in (your saved login)

Both are listed in .gitignore so they are never uploaded to GitHub.
To keep them somewhere else entirely, set the CLOUDPOD_CREDENTIALS_DIR
environment variable to that folder's path.
"""

import os

from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Read-only access to your Drive files. CloudPod can never change or delete anything.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_DIR = os.environ.get(
    "CLOUDPOD_CREDENTIALS_DIR", os.path.join(BASE_DIR, "credentials")
)
CLIENT_SECRET_FILE = os.path.join(CREDENTIALS_DIR, "credentials.json")
TOKEN_FILE = os.path.join(CREDENTIALS_DIR, "token.json")


class AuthError(Exception):
    """Raised when we can't sign in to Google. The message is safe to show the user."""


def _save_token(creds):
    os.makedirs(CREDENTIALS_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())


def sign_out():
    """Forget the saved login (the next call to get_credentials will ask you to sign in)."""
    if os.path.isfile(TOKEN_FILE):
        os.remove(TOKEN_FILE)


def _run_login_flow():
    """Open the browser so you can sign in and allow CloudPod to read your Drive."""
    if not os.path.isfile(CLIENT_SECRET_FILE):
        raise AuthError(
            "Missing credentials.json.\n"
            f"  Expected at: {CLIENT_SECRET_FILE}\n"
            "  Download your OAuth client file from Google Cloud Console "
            "(APIs & Services > Credentials) and save it there."
        )

    try:
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    except (ValueError, KeyError):
        raise AuthError(
            "credentials.json doesn't look like a valid OAuth client file. "
            "Make sure you downloaded it for a 'Desktop app' client."
        )

    print("Opening your browser to sign in to Google...")
    try:
        creds = flow.run_local_server(port=0)
    except Exception as e:
        raise AuthError(f"Google sign-in failed or was cancelled: {e}")

    _save_token(creds)
    return creds


def get_credentials():
    """Return valid Google credentials, signing in or refreshing only when needed."""
    creds = None

    if os.path.isfile(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except (ValueError, KeyError):
            creds = None  # token file is damaged: just sign in again

    # 1) Saved login is still good.
    if creds and creds.valid:
        return creds

    # 2) Login expired, but Google lets us renew it silently.
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
            return creds
        except TransportError:
            raise AuthError(
                "Couldn't reach Google to renew your login. Check your internet connection."
            )
        except RefreshError:
            print("Your Google login has expired or was revoked. Please sign in again.")
            sign_out()

    # 3) No usable login: do the full browser sign-in.
    return _run_login_flow()
