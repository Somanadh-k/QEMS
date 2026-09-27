"""One-time helper to obtain a Gmail OAuth refresh token for QEMS notifications.

Run locally (never on a server) after creating an OAuth client in Google Cloud Console --
see backend/README.md "Gmail notification setup" for the full walkthrough. This opens a
browser for the consent screen and prints the refresh token to paste into .env as
GOOGLE_REFRESH_TOKEN. It is never stored anywhere by this script.

IMPORTANT: this listens on a FIXED port (not a random one) because Google validates the
redirect URI against what you registered on the OAuth client. Before running this, add
    http://localhost:8765/
to that client's "Authorized redirect URIs" in Google Cloud Console -- Credentials ->
your OAuth 2.0 Client ID -> Authorized redirect URIs -> Add URI -> Save. Skipping this
step is the #1 cause of "Error 400: redirect_uri_mismatch".

Usage:
    python -m scripts.gmail_oauth_setup

Requires GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET already set in the environment or .env.
"""

from app.core.config import get_settings

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

# Must exactly match an "Authorized redirect URI" registered on the OAuth client --
# see the module docstring. Change this only if you registered a different port there.
LOCAL_REDIRECT_PORT = 8765


def main() -> None:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise SystemExit(
            "Missing google-auth-oauthlib. Run: pip install google-auth-oauthlib"
        ) from exc

    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise SystemExit("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET before running this.")

    redirect_uri = f"http://localhost:{LOCAL_REDIRECT_PORT}/"
    print(f"Make sure {redirect_uri} is registered as an Authorized redirect URI on this")
    print("OAuth client in Google Cloud Console, then approve the consent screen that opens.\n")

    client_config = {
        "installed": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    credentials = flow.run_local_server(port=LOCAL_REDIRECT_PORT)

    print("\nSuccess. Add this to backend/.env:\n")
    print(f"GOOGLE_REFRESH_TOKEN={credentials.refresh_token}")


if __name__ == "__main__":
    main()
