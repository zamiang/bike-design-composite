resource "google_project_iam_member" "runtime_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "deployer_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_project_iam_member" "deployer_artifactregistry_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# infra-plan / infra-apply workflows run `terraform init` as the deployer SA,
# which needs read/write on the GCS state bucket. The bucket itself is created
# out-of-band in bootstrap (see infra/README.md), so this is the bucket-scoped
# IAM binding that lets CI use it.
resource "google_storage_bucket_iam_member" "deployer_tfstate_object_user" {
  bucket = var.tfstate_bucket
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.deployer.email}"
}

# objectUser covers reading/writing/deleting the state objects themselves but
# not listing the bucket, which `terraform init` does to enumerate workspaces.
resource "google_storage_bucket_iam_member" "deployer_tfstate_legacy_reader" {
  bucket = var.tfstate_bucket
  role   = "roles/storage.legacyBucketReader"
  member = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "deployer_actas_runtime" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "wif_deployer" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/projects/${local.project_number}/locations/global/workloadIdentityPools/${var.wif_pool_id}/attribute.repository/${var.github_repo}"
}

resource "google_project_iam_member" "claude_reviewer_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.claude_reviewer.email}"
}

resource "google_service_account_iam_member" "wif_claude_reviewer" {
  service_account_id = google_service_account.claude_reviewer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/projects/${local.project_number}/locations/global/workloadIdentityPools/${var.wif_pool_id}/attribute.repository/${var.github_repo}"
}
