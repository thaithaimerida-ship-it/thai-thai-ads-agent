#!/bin/bash
# Thai Thai Ads Agent — Google Cloud Run Deploy Script
# Run this after: gcloud init

set -e

PROJECT_ID=$(gcloud config get-value project)
SERVICE_NAME="thai-thai-ads-agent"
REGION="us-central1"
IMAGE="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "Deploying to project: $PROJECT_ID"
echo "Service: $SERVICE_NAME"
echo "Region: $REGION"

# Build and push image
gcloud builds submit --tag $IMAGE .

# Deploy to Cloud Run
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 2 \
  --set-env-vars "GOOGLE_ADS_DEVELOPER_TOKEN=$GOOGLE_ADS_DEVELOPER_TOKEN" \
  --set-env-vars "GOOGLE_ADS_CLIENT_ID=$GOOGLE_ADS_CLIENT_ID" \
  --set-env-vars "GOOGLE_ADS_CLIENT_SECRET=$GOOGLE_ADS_CLIENT_SECRET" \
  --set-env-vars "GOOGLE_ADS_REFRESH_TOKEN=$GOOGLE_ADS_REFRESH_TOKEN" \
  --set-env-vars "GOOGLE_ADS_LOGIN_CUSTOMER_ID=$GOOGLE_ADS_LOGIN_CUSTOMER_ID" \
  --set-env-vars "GOOGLE_ADS_TARGET_CUSTOMER_ID=$GOOGLE_ADS_TARGET_CUSTOMER_ID" \
  --set-env-vars "GOOGLE_ADS_USE_PROTO_PLUS=True" \
  --set-env-vars "GA4_PROPERTY_ID=$GA4_PROPERTY_ID" \
  --set-env-vars "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY" \
  --set-env-vars "EMAIL_SENDER=$EMAIL_SENDER" \
  --set-env-vars "EMAIL_APP_PASSWORD=$EMAIL_APP_PASSWORD" \
  --set-env-vars "EMAIL_RESTAURANT=$EMAIL_RESTAURANT" \
  --set-env-vars "EMAIL_REPORT_TO=$EMAIL_REPORT_TO" \
  --set-env-vars "GOOGLE_SHEETS_SPREADSHEET_ID=$GOOGLE_SHEETS_SPREADSHEET_ID"

echo ""
echo "Deploy complete! Service URL:"
gcloud run services describe $SERVICE_NAME --region $REGION --format="value(status.url)"
