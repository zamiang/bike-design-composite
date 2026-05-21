output "service_url" {
  description = "Public HTTPS URL of the Cloud Run service."
  value       = google_cloud_run_v2_service.app.uri
}

output "image_repo" {
  description = "Artifact Registry repo URL (push images here)."
  value       = local.image_repo_url
}

output "runtime_service_account" {
  value = google_service_account.runtime.email
}

output "deployer_service_account" {
  value = google_service_account.deployer.email
}

output "wif_provider_resource_name" {
  description = "Full resource name to pass to google-github-actions/auth as workload_identity_provider."
  value       = "projects/${local.project_number}/locations/global/workloadIdentityPools/${var.wif_pool_id}/providers/github-provider"
}
