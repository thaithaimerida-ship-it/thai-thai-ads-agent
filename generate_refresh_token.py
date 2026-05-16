"""
Regenera el refresh_token de Google Ads.

NO contiene credenciales hardcodeadas: lee client_id / client_secret del
google-ads.yaml (gitignored). Para emitir un token nuevo, asegurate de que
el yaml tenga el client_id + client_secret correctos y ejecuta este script;
completa el consentimiento en el navegador con la cuenta de Google que tiene
acceso al Google Ads de Thai Thai (4021070209). Imprime el refresh_token.

Luego copia el token impreso a:
  - google-ads.yaml  (campo refresh_token)
  - Cloud Run env var GOOGLE_ADS_REFRESH_TOKEN
"""
import os
import yaml
from google_auth_oauthlib.flow import InstalledAppFlow

YAML_PATH = os.path.join(os.path.dirname(__file__), "google-ads.yaml")
SCOPES = ["https://www.googleapis.com/auth/adwords"]

with open(YAML_PATH, encoding="utf-8-sig") as f:
    cfg = yaml.safe_load(f)

client_id = cfg["client_id"]
client_secret = cfg["client_secret"]
if not client_id or not client_secret:
    raise SystemExit("Falta client_id o client_secret en google-ads.yaml")

print(f"Usando client_id: {client_id}")

client_config = {
    "installed": {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
# prompt=consent fuerza que Google devuelva refresh_token aunque ya hubieras
# autorizado antes; access_type=offline lo hace persistente.
credentials = flow.run_local_server(
    port=0,
    access_type="offline",
    prompt="consent",
    open_browser=True,
)

print("\n" + "=" * 60)
print("NUEVO REFRESH TOKEN:")
print("=" * 60)
print(credentials.refresh_token)
print("=" * 60)
print("len:", len(credentials.refresh_token or ""))
print("\nCopialo a: google-ads.yaml (refresh_token) + Cloud Run env GOOGLE_ADS_REFRESH_TOKEN")
