#!/bin/bash
# Thai Thai Ads Agent — Google Cloud Run Deploy Script
# Run this after: gcloud init

set -e

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

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
  --update-env-vars "GOOGLE_ADS_DEVELOPER_TOKEN=$GOOGLE_ADS_DEVELOPER_TOKEN" \
  --update-env-vars "GOOGLE_ADS_CLIENT_ID=$GOOGLE_ADS_CLIENT_ID" \
  --update-env-vars "GOOGLE_ADS_CLIENT_SECRET=$GOOGLE_ADS_CLIENT_SECRET" \
  --update-env-vars "GOOGLE_ADS_REFRESH_TOKEN=$GOOGLE_ADS_REFRESH_TOKEN" \
  --update-env-vars "GOOGLE_ADS_LOGIN_CUSTOMER_ID=$GOOGLE_ADS_LOGIN_CUSTOMER_ID" \
  --update-env-vars "GOOGLE_ADS_TARGET_CUSTOMER_ID=$GOOGLE_ADS_TARGET_CUSTOMER_ID" \
  --update-env-vars "GOOGLE_ADS_USE_PROTO_PLUS=True" \
  --update-env-vars "GA4_PROPERTY_ID=$GA4_PROPERTY_ID" \
  --update-env-vars "OPENAI_API_KEY=$OPENAI_API_KEY" \
  --update-env-vars "EMAIL_SENDER=$EMAIL_SENDER" \
  --update-env-vars "EMAIL_APP_PASSWORD=$EMAIL_APP_PASSWORD" \
  --update-env-vars "EMAIL_RESTAURANT=$EMAIL_RESTAURANT" \
  --update-env-vars "EMAIL_REPORT_TO=$EMAIL_REPORT_TO" \
  --update-env-vars "CALLMEBOT_PHONE=$CALLMEBOT_PHONE" \
  --update-env-vars "CALLMEBOT_APIKEY=$CALLMEBOT_APIKEY" \
  --update-env-vars "GOOGLE_SHEETS_SPREADSHEET_ID=$GOOGLE_SHEETS_SPREADSHEET_ID"

echo ""
echo "Deploy complete! Service URL:"
gcloud run services describe $SERVICE_NAME --region $REGION --format="value(status.url)"
