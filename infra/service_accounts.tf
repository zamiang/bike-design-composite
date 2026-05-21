resource "google_service_account" "runtime" {
  account_id   = "paint-preview-runtime"
  display_name = "Scarab Paint Preview — Cloud Run runtime"
  description  = "Attached to the Cloud Run service. Calls Vertex AI; reads APP_PASSWORD / SESSION_SECRET from Secret Manager."
}

resource "google_service_account" "deployer" {
  account_id   = "paint-preview-deployer"
  display_name = "Scarab Paint Preview — GitHub Actions deployer"
  description  = "Impersonated from GitHub Actions via Workload Identity Federation."
}

resource "google_service_account" "claude_reviewer" {
  account_id   = "claude-reviewer"
  display_name = "Claude Code reviewer (GitHub Actions)"
  description  = "Impersonated from GitHub Actions to call Claude on Vertex AI for PR reviews and @claude mentions. Scoped to aiplatform.user only."
}
