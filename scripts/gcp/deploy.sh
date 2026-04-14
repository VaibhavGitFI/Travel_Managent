#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID before running this script}"
REGION="${REGION:-asia-south1}"
SERVICE_NAME="${SERVICE_NAME:-travelsync-pro}"
AR_REPOSITORY="${AR_REPOSITORY:-travelsync}"
IMAGE_NAME="${IMAGE_NAME:-app}"
RUNTIME_SERVICE_ACCOUNT="${RUNTIME_SERVICE_ACCOUNT:-travelsync-runtime@${PROJECT_ID}.iam.gserviceaccount.com}"
ALLOW_UNAUTHENTICATED="${ALLOW_UNAUTHENTICATED:-true}"
CPU="${CPU:-2}"
MEMORY="${MEMORY:-2Gi}"
MIN_INSTANCES="${MIN_INSTANCES:-1}"
MAX_INSTANCES="${MAX_INSTANCES:-10}"
CONCURRENCY="${CONCURRENCY:-80}"
TIMEOUT="${TIMEOUT:-300}"
AMADEUS_ENV="${AMADEUS_ENV:-production}"
CLOUDSQL_INSTANCE="${CLOUDSQL_INSTANCE:-}"
VPC_CONNECTOR="${VPC_CONNECTOR:-}"

if [[ -z "$CLOUDSQL_INSTANCE" ]]; then
  echo "No CLOUDSQL_INSTANCE set — deploying without Cloud SQL attachment (using external DB via DATABASE_URL secret)."
fi

# COMMIT_SHA is a Cloud Build built-in that's auto-populated by GitHub triggers
# but is empty for manual gcloud builds submit. Derive it from git when running locally.
_LOCAL_COMMIT_SHA="${COMMIT_SHA:-$(git rev-parse HEAD 2>/dev/null || echo 'manual')}"

SUBSTITUTIONS=(
  "COMMIT_SHA=${_LOCAL_COMMIT_SHA}"
  "_SERVICE_NAME=${SERVICE_NAME}"
  "_REGION=${REGION}"
  "_AR_REPOSITORY=${AR_REPOSITORY}"
  "_IMAGE_NAME=${IMAGE_NAME}"
  "_RUNTIME_SERVICE_ACCOUNT=${RUNTIME_SERVICE_ACCOUNT}"
  "_ALLOW_UNAUTHENTICATED=${ALLOW_UNAUTHENTICATED}"
  "_CPU=${CPU}"
  "_MEMORY=${MEMORY}"
  "_MIN_INSTANCES=${MIN_INSTANCES}"
  "_MAX_INSTANCES=${MAX_INSTANCES}"
  "_CONCURRENCY=${CONCURRENCY}"
  "_TIMEOUT=${TIMEOUT}"
  "_AMADEUS_ENV=${AMADEUS_ENV}"
  "_CLOUDSQL_INSTANCE=${CLOUDSQL_INSTANCE}"
)

if [[ -n "$VPC_CONNECTOR" ]]; then
  SUBSTITUTIONS+=("_VPC_CONNECTOR=${VPC_CONNECTOR}")
fi

echo "==> Submitting Cloud Build for ${SERVICE_NAME}"
gcloud builds submit \
  --project "$PROJECT_ID" \
  --config cloudbuild.yaml \
  --substitutions "$(IFS=,; echo "${SUBSTITUTIONS[*]}")"
