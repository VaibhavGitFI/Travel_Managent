#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/gcp/setup-github-actions.sh
#
# One-time setup: provisions the GCP resources GitHub Actions needs to deploy
# to Cloud Run without storing any long-lived service-account JSON keys.
#
# What this creates:
#   1. Workload Identity Pool  — github-pool
#   2. OIDC Provider           — github-provider (trusts token.actions.githubusercontent.com)
#   3. Deployer service account — github-deployer@PROJECT_ID.iam.gserviceaccount.com
#   4. IAM bindings:
#       - deployer → Artifact Registry Writer
#       - deployer → Cloud Run Admin
#       - deployer → Service Account User (on travelsync-runtime SA)
#       - deployer → WIF impersonation scoped to THIS repo only
#
# Prerequisites:
#   - gcloud auth login (user must have Project Owner or a custom role with
#     iam.workloadIdentityPools.create + iam.serviceAccounts.create)
#   - bootstrap.sh already run (runtime SA must exist)
#
# Usage:
#   PROJECT_ID=my-project-123 \
#   GITHUB_ORG=VaibhavGitFI \
#   GITHUB_REPO=Travel_Managent \
#   ./scripts/gcp/setup-github-actions.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Required inputs ────────────────────────────────────────────────────────
PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID before running this script}"
GITHUB_ORG="${GITHUB_ORG:?Set GITHUB_ORG (your GitHub username or org, e.g. VaibhavGitFI)}"
GITHUB_REPO="${GITHUB_REPO:?Set GITHUB_REPO (repository name, e.g. Travel_Managent)}"

# ── Tunable defaults ───────────────────────────────────────────────────────
REGION="${REGION:-asia-south1}"
RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-travelsync-runtime}"
DEPLOYER_SA_NAME="${DEPLOYER_SA_NAME:-github-deployer}"
POOL_NAME="${POOL_NAME:-github-pool}"
PROVIDER_NAME="${PROVIDER_NAME:-github-provider}"
AR_REPOSITORY="${AR_REPOSITORY:-travelsync}"

# ── Derived values ─────────────────────────────────────────────────────────
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
DEPLOYER_SA="${DEPLOYER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
WIF_POOL_RESOURCE="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_NAME}"
WIF_PROVIDER_RESOURCE="${WIF_POOL_RESOURCE}/providers/${PROVIDER_NAME}"

echo "==> Project:       $PROJECT_ID  (number: $PROJECT_NUMBER)"
echo "==> GitHub repo:   ${GITHUB_ORG}/${GITHUB_REPO}"
echo "==> Deployer SA:   $DEPLOYER_SA"
echo ""

# ── 1. Enable required APIs (idempotent) ──────────────────────────────────
echo "==> Enabling APIs..."
gcloud services enable \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  --project "$PROJECT_ID"

# ── 2. Workload Identity Pool ──────────────────────────────────────────────
echo "==> Creating Workload Identity Pool: $POOL_NAME"
if gcloud iam workload-identity-pools describe "$POOL_NAME" \
    --project="$PROJECT_ID" --location=global >/dev/null 2>&1; then
  echo "    Pool already exists — skipping."
else
  gcloud iam workload-identity-pools create "$POOL_NAME" \
    --project="$PROJECT_ID" \
    --location=global \
    --display-name="GitHub Actions" \
    --description="Keyless auth for GitHub Actions CI/CD"
fi

# ── 3. OIDC Provider (GitHub token.actions.githubusercontent.com) ──────────
echo "==> Creating OIDC provider: $PROVIDER_NAME"
if gcloud iam workload-identity-pools providers describe "$PROVIDER_NAME" \
    --project="$PROJECT_ID" \
    --location=global \
    --workload-identity-pool="$POOL_NAME" >/dev/null 2>&1; then
  echo "    Provider already exists — skipping."
else
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_NAME" \
    --project="$PROJECT_ID" \
    --location=global \
    --workload-identity-pool="$POOL_NAME" \
    --display-name="GitHub OIDC" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="\
google.subject=assertion.sub,\
attribute.actor=assertion.actor,\
attribute.repository=assertion.repository,\
attribute.repository_owner=assertion.repository_owner" \
    --attribute-condition="assertion.repository_owner=='${GITHUB_ORG}'"
    # attribute-condition scopes this provider to YOUR GitHub org only.
    # Even if another org knows your pool ID, their tokens are rejected.
fi

# ── 4. Deployer service account ────────────────────────────────────────────
echo "==> Ensuring deployer service account: $DEPLOYER_SA"
if ! gcloud iam service-accounts describe "$DEPLOYER_SA" \
    --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$DEPLOYER_SA_NAME" \
    --display-name="GitHub Actions deployer" \
    --project "$PROJECT_ID"
fi

# ── 5. IAM bindings for the deployer SA ───────────────────────────────────
echo "==> Granting IAM roles to deployer SA..."

# Push images to Artifact Registry
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOYER_SA}" \
  --role="roles/artifactregistry.writer" \
  --condition=None \
  >/dev/null

# Deploy Cloud Run services
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOYER_SA}" \
  --role="roles/run.admin" \
  --condition=None \
  >/dev/null

# Read service status / logs (needed for health-check step in deploy.yml)
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOYER_SA}" \
  --role="roles/run.viewer" \
  --condition=None \
  >/dev/null

# Act as the runtime SA when specifying --service-account in gcloud run deploy
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:${DEPLOYER_SA}" \
  --role="roles/iam.serviceAccountUser" \
  >/dev/null

# ── 6. Bind WIF provider → deployer SA (scoped to this repo only) ─────────
# Only tokens for github.com/${GITHUB_ORG}/${GITHUB_REPO} can impersonate the
# deployer SA. Other repos in the same org cannot.
echo "==> Binding WIF provider to deployer SA (repo: ${GITHUB_ORG}/${GITHUB_REPO})..."
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER_SA" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${WIF_POOL_RESOURCE}/attribute.repository/${GITHUB_ORG}/${GITHUB_REPO}" \
  >/dev/null

# ── 7. Print GitHub Secrets ────────────────────────────────────────────────
cat <<EOF

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Setup complete. Add these secrets to GitHub:
  Settings → Secrets and variables → Actions → New repository secret
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  GCP_PROJECT_ID          = ${PROJECT_ID}

  WIF_PROVIDER            = ${WIF_PROVIDER_RESOURCE}

  WIF_SERVICE_ACCOUNT     = ${DEPLOYER_SA}

  CLOUDSQL_INSTANCE       = ${PROJECT_ID}:${REGION}:travelsync-db
  (Replace "travelsync-db" with your actual Cloud SQL instance name)

  RUNTIME_SERVICE_ACCOUNT = ${RUNTIME_SA}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Optional: set up branch protection on main
  Settings → Branches → Add rule → Branch: main
    ✓ Require a pull request before merging
    ✓ Require status checks: backend-lint, backend-test, frontend-build
    ✓ Require branches to be up to date before merging
    ✓ Include administrators
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EOF
