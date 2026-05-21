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

Then grab the project number, you'll need it for the workflow:

```sh
gcloud projects describe "$PROJECT" --format='value(projectNumber)'
```

Edit `.github/workflows/deploy.yml` and replace `PROJECT_NUMBER` in `WIF_PROVIDER` with that number.

## First apply

The `image` variable defaults to GCP's `hello` container so the first apply works before any app image exists.

```sh
cd infra
terraform init
terraform apply
```

You should see a `service_url` output pointing to a `*.run.app` URL that serves the hello-world page. From here on, every push to `main` rebuilds the image and rolls a new revision.

## Local deploys (skip GitHub Actions)

```sh
SHA=$(git rev-parse --short HEAD)
IMAGE="us-central1-docker.pkg.dev/time-279118/scarab-paint-preview/app:${SHA}"

gcloud auth configure-docker us-central1-docker.pkg.dev
docker build -t "$IMAGE" ../web
docker push "$IMAGE"

terraform apply -var="image=$IMAGE"
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
