# infra

Terraform for the Scarab paint-preview Cloud Run service.

## One-time bootstrap

Some resources have to exist before Terraform can run (state bucket, WIF pool) or have values that shouldn't live in code (secret payloads). Do these once, from your laptop, authenticated as a project owner.

```sh
PROJECT=time-279118
REGION=us-central1
REPO=zamiang/bike-design-composite

gcloud config set project "$PROJECT"
gcloud auth login
gcloud auth application-default login
```

### 1. State bucket

```sh
gsutil mb -p "$PROJECT" -l "$REGION" "gs://${PROJECT}-tfstate-bike-design"
gsutil versioning set on "gs://${PROJECT}-tfstate-bike-design"
```

### 2. Enable the APIs Terraform itself needs to read

```sh
gcloud services enable \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  serviceusage.googleapis.com
```

Terraform manages the rest (Run, Artifact Registry, Secret Manager, Vertex AI).

### 3. Secret values

Terraform creates the secret *resources* but never sees their values. Seed them now:

```sh
printf "%s" "$(openssl rand -base64 24)" | gcloud secrets create APP_PASSWORD --data-file=-
printf "%s" "$(openssl rand -base64 32)" | gcloud secrets create SESSION_SECRET --data-file=-
```

Save the `APP_PASSWORD` value somewhere; it's how you'll sign in to the app.

To rotate later: `gcloud secrets versions add APP_PASSWORD --data-file=-`. Cloud Run re-reads `latest` on the next revision.

### 4. Workload Identity Federation for GitHub Actions

```sh
gcloud iam workload-identity-pools create github-pool \
  --location=global \
  --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global \
  --workload-identity-pool=github-pool \
  --display-name="GitHub OIDC" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository == '${REPO}'"
```

Then publish the project number as a GitHub repo variable so the workflows can build the `WIF_PROVIDER` resource name themselves:

```sh
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
gh variable set GCP_PROJECT_NUMBER --body "$PROJECT_NUMBER"
```

(Set it once per repo. The workflows fail loudly with a clear message if it's missing.)

## First apply

The `image` variable defaults to GCP's `hello` container so the first apply works before any app image exists.

```sh
cd infra
terraform init
terraform apply
```

You should see a `service_url` output pointing to a `*.run.app` URL that serves the hello-world page.

### 5. Grant the deployer SA access to the state bucket

The first `terraform apply` (above, from your laptop as owner) creates the `paint-preview-deployer` service account. For the GitHub Actions `infra-plan` / `infra-apply` workflows to run `terraform init` as that SA, it needs read/write on the state bucket. Terraform can't bootstrap this for itself: `init` reads the bucket before any resource is evaluated.

```sh
DEPLOYER=paint-preview-deployer@${PROJECT}.iam.gserviceaccount.com
BUCKET=gs://${PROJECT}-tfstate-bike-design

gcloud storage buckets add-iam-policy-binding "$BUCKET" \
  --member="serviceAccount:${DEPLOYER}" \
  --role="roles/storage.objectUser"

gcloud storage buckets add-iam-policy-binding "$BUCKET" \
  --member="serviceAccount:${DEPLOYER}" \
  --role="roles/storage.legacyBucketReader"
```

After this, the bindings are also tracked in `iam.tf` so subsequent terraform runs reconcile them; the manual grant is only needed because of the chicken-and-egg with the state backend.

## How deploys roll after bootstrap

Two pipelines, deliberately separate:

- **App code (`web/**`)**: every push to `main` runs `.github/workflows/deploy-app.yml`, which builds a new image, pushes it, and calls `gcloud run deploy` to roll a revision. Terraform is not invoked. The `image` field on the Cloud Run service is in `ignore_changes`, so Terraform won't fight the app pipeline.
- **Infra (`infra/**`)**: opening a PR runs `.github/workflows/infra-plan.yml`, which posts a `terraform plan` as a sticky PR comment. Nothing is applied. After merging, run `.github/workflows/infra-apply.yml` manually from the Actions tab. Wire that workflow's `production` environment in repo settings to require reviewer approval if you want a second pair of eyes.

This split keeps a bad infra PR from rolling out alongside an app change. Image rolls are fast and low-risk; infra rolls are slow and manual.

## Local deploys (skip GitHub Actions)

App-only:

```sh
SHA=$(git rev-parse --short HEAD)
IMAGE="us-central1-docker.pkg.dev/time-279118/scarab-paint-preview/app:${SHA}"

gcloud auth configure-docker us-central1-docker.pkg.dev
docker build -t "$IMAGE" ../web
docker push "$IMAGE"
gcloud run deploy scarab-paint-preview --image="$IMAGE" --region=us-central1
```

Infra-only:

```sh
cd infra
terraform apply
```

## What's where

| Concern | File |
|---|---|
| Backend (GCS state) | `backend.tf` |
| Variables | `variables.tf` |
| APIs to enable | `apis.tf` |
| Artifact Registry repo | `artifact_registry.tf` |
| Secret resources | `secrets.tf` |
| Service accounts | `service_accounts.tf` |
| Role bindings + WIF | `iam.tf` |
| The Cloud Run service | `cloud_run.tf` |
| Outputs (URL etc.) | `outputs.tf` |

## Tuning knobs (in `cloud_run.tf`)

- **`timeout = "900s"`**: max single-request duration. Compositing several bases serially eats minutes; don't drop this.
- **`max_instance_request_concurrency = 4`**: image generation is CPU-heavy. Higher concurrency on one instance starves and 504s.
- **`max_instance_count = 3`**: hard cap on parallel Cloud Run instances; combined with concurrency=4, ceiling is 12 in-flight requests. Each composite costs ~$0.15 to Vertex, so this is also a spend cap.
- **`min_instance_count = 0`**: cold starts are fine for a sporadic-traffic, password-gated tool.
