resource "google_cloud_run_v2_service" "app" {
  name     = var.service_name
  location = var.region

  deletion_protection = false

  template {
    service_account = google_service_account.runtime.email

    timeout = "900s"

    # Results are cached in-process on the instance that served /generate, then
    # served back over follow-up GETs to /result/{job_id}/.... Session affinity
    # keeps those follow-ups on the same instance so the cache hits.
    session_affinity = true

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    max_instance_request_concurrency = 4

    containers {
      image = var.image

      resources {
        limits = {
          cpu    = "2"
          memory = "1Gi"
        }
        startup_cpu_boost = true
      }

      ports {
        container_port = 8080
      }

      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }

      env {
        name  = "GCP_LOCATION"
        value = "global"
      }

      env {
        name = "APP_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.app_password.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "SESSION_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.session_secret.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.services,
    google_secret_manager_secret_iam_member.runtime_app_password,
    google_secret_manager_secret_iam_member.runtime_session_secret,
    google_project_iam_member.runtime_aiplatform_user,
  ]

  lifecycle {
    ignore_changes = [
      client,
      client_version,
      # Image is rolled by the deploy-app workflow via `gcloud run deploy`.
      # Terraform owns the rest of the service config; it should not fight the app pipeline.
      template[0].containers[0].image,
    ]
  }
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = google_cloud_run_v2_service.app.project
  location = google_cloud_run_v2_service.app.location
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
