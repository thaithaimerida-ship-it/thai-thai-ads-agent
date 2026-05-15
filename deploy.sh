#!/bin/bash
# Thai Thai Ads Agent — Google Cloud Run Deploy (SOLO CÓDIGO)
# Run this after: gcloud init
#
# ============================================================
# POLÍTICA DE ENV VARS (decisión 15-may-2026):
#   Las variables de entorno se gestionan EXCLUSIVAMENTE en la
#   consola de Cloud Run (o `gcloud run services update --update-env-vars`
#   de forma manual y deliberada). Este script NUNCA toca env vars.
#
#   Razón: el deploy.sh anterior cargaba el .env local y hacía
#   --update-env-vars VAR=$VAR para cada variable. Si el .env local
#   estaba incompleto (caso real 12-may y 15-may), pisaba variables
#   críticas de producción (GA4_PROPERTY_ID, GOOGLE_ADS_DEVELOPER_TOKEN)
#   con cadenas vacías y rompía el servicio.
#
#   Cloud Run preserva automáticamente las env vars de la revisión
#   activa cuando se hace deploy SIN --update-env-vars. Por eso este
#   script solo actualiza el código (la imagen) y nada más.
#
#   Para cambiar una env var: hazlo en la consola de Cloud Run,
#   NUNCA agregando --update-env-vars aquí.
# ============================================================

set -e

PROJECT_ID=$(gcloud config get-value project)
SERVICE_NAME="thai-thai-ads-agent"
REGION="us-central1"
IMAGE="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "Deploying to project: $PROJECT_ID"
echo "Service: $SERVICE_NAME"
echo "Region: $REGION"
echo "Modo: SOLO CÓDIGO (env vars preservadas por Cloud Run, no se tocan)"

# Build and push image
gcloud builds submit --tag $IMAGE .

# Deploy SOLO código — sin --update-env-vars ni --set-env-vars.
# Cloud Run preserva las env vars de la revisión actual intactas.
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 2

echo ""
echo "Deploy complete! Service URL:"
gcloud run services describe $SERVICE_NAME --region $REGION --format="value(status.url)"
