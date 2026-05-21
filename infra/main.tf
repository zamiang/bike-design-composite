provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "this" {}

locals {
  project_number = data.google_project.this.number
  image_repo_url = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_repo}"
}
