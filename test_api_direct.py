from google.ads.googleads.client import GoogleAdsClient
import os

# Configurar credenciales
os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"] = "81iNAdWjK5Md18Knkk1IpA"
os.environ["GOOGLE_ADS_CLIENT_ID"] = "399022260320-3ipufkckol5sa2t1ojf8jm9bpucqdoqt.apps.googleusercontent.com"
os.environ["GOOGLE_ADS_CLIENT_SECRET"] = "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"
os.environ["GOOGLE_ADS_REFRESH_TOKEN"] = "1//05yeRzRWfcPWNCgYIARAAGAUSNwF-L9IrIIqzAh7JzWrdnLEizG8tic1YjivAldCFpJkoIC8auOeMUg15dMG0-VadNIwRYUiNfPI"
os.environ["GOOGLE_ADS_USE_PROTO_PLUS"] = "True"

print("🔍 Creando cliente...")
client = GoogleAdsClient.load_from_env()

print("✅ Cliente creado")

# Probar con SOLO el customer ID, sin query complejas
customer_id = "4021070209"

print(f"\n🔍 Intentando acceso básico a cuenta {customer_id}...")

try:
    customer_service = client.get_service("GoogleAdsService")
    
    # Query MUY simple - solo nombre de campaña
    query = """
        SELECT campaign.name
        FROM campaign
        LIMIT 1
    """
    
    response = customer_service.search(customer_id=customer_id, query=query)
    
    print("\n🎉 ¡ÉXITO! Campañas encontradas:")
    for row in response:
        print(f"  - {row.campaign.name}")
        
except Exception as e:
    print(f"\n❌ ERROR:")
    print(f"{e}")
    print("\n💡 Esto confirma que el problema está en la configuración de la cuenta,")
    print("   no en las credenciales.")