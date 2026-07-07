#!/usr/bin/env python3
"""
GalleryForge - DeviantArt OAuth2.1 (PKCE) Authentifizierung.
 
Einmalig ausführen, um einen Refresh-Token zu holen:
    python3 -m core.da_auth
 
Danach liefert get_valid_access_token() immer einen frischen Access-Token
(erneuert ihn automatisch via Refresh-Token, wenn er abgelaufen ist).
 
Speichern als: core/da_auth.py
"""
 
import base64
import hashlib
import http.server
import json
import secrets
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs
 
import requests
 
CONFIG_DIR = Path.home() / ".config" / "galleryforge"
CREDENTIALS_FILE = CONFIG_DIR / "da_credentials.json"
TOKENS_FILE = CONFIG_DIR / "da_tokens.json"
 
AUTHORIZE_URL = "https://www.deviantart.com/oauth2/authorize"
TOKEN_URL = "https://www.deviantart.com/oauth2/token"
SCOPE = "stash publish"
 
 
def load_credentials() -> dict:
    if not CREDENTIALS_FILE.exists():
        raise SystemExit(
            f"FEHLER: {CREDENTIALS_FILE} nicht gefunden.\n"
            "Erst client_id/client_secret/redirect_uri dort eintragen."
        )
    return json.loads(CREDENTIALS_FILE.read_text())
 
 
def save_tokens(tokens: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tokens["obtained_at"] = time.time()
    TOKENS_FILE.write_text(json.dumps(tokens, indent=2))
    TOKENS_FILE.chmod(0o600)
 
 
def load_tokens() -> dict | None:
    if not TOKENS_FILE.exists():
        return None
    return json.loads(TOKENS_FILE.read_text())
 
 
def generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge
 
 
class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    result: dict = {}
 
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        _CallbackHandler.result["code"] = params.get("code", [None])[0]
        _CallbackHandler.result["state"] = params.get("state", [None])[0]
        _CallbackHandler.result["error"] = params.get("error", [None])[0]
 
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
 
        if _CallbackHandler.result["code"] and not _CallbackHandler.result["error"]:
            msg = "GalleryForge: Autorisierung erhalten. Du kannst dieses Tab jetzt schliessen."
        else:
            msg = (
                "GalleryForge: Kein gueltiger Code erhalten. "
                "Bitte die zuletzt im Terminal gedruckte URL frisch oeffnen "
                "(nicht aus Browser-Verlauf/Autovervollstaendigung)."
            )
        self.wfile.write(f"<html><body><h2>{msg}</h2></body></html>".encode("utf-8"))
 
    def log_message(self, fmt, *args):
        pass  # Konsole sauber halten
 
 
def run_authorize_flow():
    creds = load_credentials()
    verifier, challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(16)
 
    redirect_uri = creds["redirect_uri"]
    port = int(urlparse(redirect_uri).port)
 
    params = {
        "response_type": "code",
        "client_id": creds["client_id"],
        "redirect_uri": redirect_uri,
        "scope": SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{AUTHORIZE_URL}?{urlencode(params)}"
 
    print("Öffne diese URL in deinem Browser und logge dich bei DeviantArt ein:\n")
    print(auth_url)
    print("\nWarte auf Autorisierung...")
 
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass  # WSL2 hat ggf. keinen Browser - URL oben manuell öffnen
 
    server = http.server.HTTPServer(("localhost", port), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    thread.join(timeout=300)
    server.server_close()
 
    result = _CallbackHandler.result
    if not result.get("code"):
        raise SystemExit(f"FEHLER: Keine Autorisierung erhalten. {result}")
    if result.get("state") != state:
        raise SystemExit("FEHLER: State-Mismatch - möglicher CSRF-Versuch, abgebrochen.")
 
    print("Code erhalten, tausche gegen Access-Token...")
 
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "redirect_uri": redirect_uri,
            "code": result["code"],
            "code_verifier": verifier,
        },
        timeout=30,
    )
    response.raise_for_status()
    tokens = response.json()
 
    if "access_token" not in tokens:
        raise SystemExit(f"FEHLER: Unerwartete Token-Antwort: {tokens}")
 
    save_tokens(tokens)
    print(f"\nErfolgreich! Tokens gespeichert in {TOKENS_FILE}")
    print("Ab jetzt holt get_valid_access_token() automatisch frische Tokens.")
 
 
def refresh_access_token(tokens: dict) -> dict:
    creds = load_credentials()
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "refresh_token": tokens["refresh_token"],
        },
        timeout=30,
    )
    response.raise_for_status()
    new_tokens = response.json()
    # refresh_token bleibt bei DA meist gleich, aber falls ein neuer kommt: übernehmen
    new_tokens.setdefault("refresh_token", tokens["refresh_token"])
    save_tokens(new_tokens)
    return new_tokens
 
 
def get_valid_access_token() -> str:
    """Liefert einen gültigen Access-Token, erneuert ihn bei Bedarf automatisch."""
    tokens = load_tokens()
    if not tokens:
        raise SystemExit(
            "FEHLER: Kein gespeicherter Token. Erst einmalig ausführen:\n"
            "  python3 -m core.da_auth"
        )
 
    expires_in = tokens.get("expires_in", 3600)
    obtained_at = tokens.get("obtained_at", 0)
    # 60 Sekunden Puffer vor tatsächlichem Ablauf erneuern
    if time.time() > obtained_at + expires_in - 60:
        tokens = refresh_access_token(tokens)
 
    return tokens["access_token"]
 
 
if __name__ == "__main__":
    run_authorize_flow()
 
