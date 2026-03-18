from google_auth_oauthlib.flow import InstalledAppFlow

# NUEVAS CREDENCIALES
CLIENT_ID = "399022260320-3ipufkckol5sa2t1ojf8jm9bpucqdoqt.apps.googleusercontent.com"
CLIENT_SECRET = "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"
SCOPES = ['https://www.googleapis.com/auth/adwords']

# Crear configuración OAuth
client_config = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"]
    }
}

# Ejecutar flujo de autenticación
flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
credentials = flow.run_local_server(port=0)

print("\n" + "="*60)
print("✅ NUEVO REFRESH TOKEN GENERADO:")
print("="*60)
print(f"\n{credentials.refresh_token}\n")
print("="*60)
print("\nCopia este token y actualiza tu .env")
print("="*60)