resource "google_artifact_registry_repository" "app" {
  location      = var.region
  repository_id = var.artifact_repo
  format        = "DOCKER"
  description   = "Container images for the Scarab paint-preview Cloud Run service."

  depends_on = [google_project_service.services]
}
