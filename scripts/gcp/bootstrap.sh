#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID before running this script}"
REGION="${REGION:-asia-south1}"
AR_REPOSITORY="${AR_REPOSITORY:-travelsync}"
RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-travelsync-runtime}"

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUNTIME_SERVICE_ACCOUNT="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
BUILD_SERVICE_ACCOUNT="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

echo "==> Using project: $PROJECT_ID"
echo "==> Using region:  $REGION"

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  iam.googleapis.com \
  compute.googleapis.com \
  vpcaccess.googleapis.com \
  --project "$PROJECT_ID"

if ! gcloud iam service-accounts describe "$RUNTIME_SERVICE_ACCOUNT" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$RUNTIME_SA_NAME" \
    --display-name="TravelSync Cloud Run runtime" \
    --project "$PROJECT_ID"
fi

if ! gcloud artifacts repositories describe "$AR_REPOSITORY" --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$AR_REPOSITORY" \
    --repository-format=docker \
    --location="$REGION" \
    --description="TravelSync production images" \
    --project "$PROJECT_ID"
fi

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor" >/dev/null

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SERVICE_ACCOUNT}" \
  --role="roles/cloudsql.client" >/dev/null

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${BUILD_SERVICE_ACCOUNT}" \
  --role="roles/run.admin" >/dev/null

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${BUILD_SERVICE_ACCOUNT}" \
  --role="roles/artifactregistry.writer" >/dev/null

gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SERVICE_ACCOUNT" \
  --member="serviceAccount:${BUILD_SERVICE_ACCOUNT}" \
  --role="roles/iam.serviceAccountUser" \
  --project "$PROJECT_ID" >/dev/null

cat <<EOF

Bootstrap complete.

Created / verified:
- Artifact Registry repo: ${AR_REPOSITORY}
- Runtime service account: ${RUNTIME_SERVICE_ACCOUNT}

Granted:
- Runtime SA -> Secret Manager Secret Accessor
- Runtime SA -> Cloud SQL Client
- Cloud Build SA -> Cloud Run Admin
- Cloud Build SA -> Artifact Registry Writer
- Cloud Build SA -> Service Account User on runtime SA

Next:
1. Create Cloud SQL and the TravelSync database.
2. Create required Secret Manager secrets:
   FLASK_SECRET_KEY
   JWT_SECRET_KEY
   DATABASE_URL
   CORS_ORIGINS
   GEMINI_API_KEY
   GOOGLE_MAPS_API_KEY
   GOOGLE_VISION_API_KEY
   AMADEUS_CLIENT_ID
   AMADEUS_CLIENT_SECRET
   OPENWEATHER_API_KEY
   OPEN_EXCHANGE_APP_ID
   REDIS_URL                 (optional)
   GCS_BUCKET                (optional)
3. Deploy with:
   PROJECT_ID=${PROJECT_ID} CLOUDSQL_INSTANCE=${PROJECT_ID}:${REGION}:YOUR_SQL_INSTANCE ./scripts/gcp/deploy.sh

EOF
