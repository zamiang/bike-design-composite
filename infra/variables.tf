variable "project_id" {
  type    = string
  default = "time-279118"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "service_name" {
  type    = string
  default = "scarab-paint-preview"
}

variable "artifact_repo" {
  type    = string
  default = "scarab-paint-preview"
}

variable "image" {
  type        = string
  description = "Full image URI for Cloud Run. CI overrides this per deploy with a SHA-tagged image. Default is GCP's hello-world container so the first `terraform apply` can succeed before any app image exists."
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "github_repo" {
  type        = string
  description = "owner/repo of the GitHub repository, used in the WIF principalSet binding."
  default     = "zamiang/bike-design-composite"
}

variable "wif_pool_id" {
  type        = string
  description = "ID of the Workload Identity Pool created during bootstrap."
  default     = "github-pool"
}

variable "tfstate_bucket" {
  type        = string
  description = "GCS bucket holding Terraform state (created during bootstrap, matches backend.tf)."
  default     = "time-279118-tfstate-bike-design"
}

variable "results_bucket" {
  type        = string
  description = "GCS bucket holding ephemeral composite results the app serves back over /result/... GETs. Created during bootstrap (see README); objects are keyed by job_id and expire via a lifecycle rule. Backing the results in a bucket (not in-process) is what lets the follow-up image GETs resolve on any Cloud Run instance."
  default     = "time-279118-scarab-paint-preview-results"
}
