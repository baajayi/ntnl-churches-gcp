terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" {
  description = "GCP Project ID"
  type        = string
  default     = "zeta-bonfire-476018-u6"
}

variable "region" {
  description = "GCP Region for resources"
  type        = string
  default     = "us-central1"
}

variable "app_name" {
  description = "Application name"
  type        = string
  default     = "ntnl-churches"
}

# ============================================================================
# Enable Required GCP APIs
# ============================================================================

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "cloudbuild.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com"
  ])

  service            = each.value
  disable_on_destroy = false
}

# ============================================================================
# Cloud Storage Bucket for Tenant-Isolated Logs
# ============================================================================

resource "google_storage_bucket" "logs" {
  name          = "${var.app_name}-logs"
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  # Auto-delete logs after 90 days (cost optimization)
  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }

  # Optional: Move to Nearline storage after 30 days
  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  depends_on = [google_project_service.apis]
}

# ============================================================================
# Artifact Registry for Docker Images
# ============================================================================

resource "google_artifact_registry_repository" "app" {
  repository_id = var.app_name
  format        = "DOCKER"
  location      = var.region
  description   = "Container images for ${var.app_name}"

  depends_on = [google_project_service.apis]
}

# ============================================================================
# Service Account for Cloud Run Runtime
# ============================================================================

resource "google_service_account" "cloudrun_runtime" {
  account_id   = "${var.app_name}-runtime"
  display_name = "Cloud Run runtime SA for ${var.app_name}"

  depends_on = [google_project_service.apis]
}

# Grant Cloud Storage objectAdmin access to logs bucket
resource "google_storage_bucket_iam_member" "logs_writer" {
  bucket = google_storage_bucket.logs.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.cloudrun_runtime.email}"
}

# Grant Secret Manager secretAccessor role
resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.cloudrun_runtime.email}"

  depends_on = [google_service_account.cloudrun_runtime]
}

# ============================================================================
# Secret Manager Secrets (values populated manually via gcloud)
# ============================================================================

resource "google_secret_manager_secret" "secrets" {
  for_each = toset([
    "OPENAI_API_KEY",
    "PINECONE_API_KEY",
    "DISCORD_TOKEN",
    "CHATBOT_API_KEY"
  ])

  secret_id = each.key

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

# ============================================================================
# Service Account for GitHub Actions Deployment
# ============================================================================

resource "google_service_account" "github_actions_deployer" {
  account_id   = "github-actions-deployer"
  display_name = "GitHub Actions deployer for CI/CD"

  depends_on = [google_project_service.apis]
}

# Grant Cloud Run admin role to deployer
resource "google_project_iam_member" "deployer_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.github_actions_deployer.email}"

  depends_on = [google_service_account.github_actions_deployer]
}

# Grant Artifact Registry writer role to deployer
resource "google_project_iam_member" "deployer_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_actions_deployer.email}"

  depends_on = [google_service_account.github_actions_deployer]
}

# Grant Service Account user role (needed to deploy Cloud Run with service account)
resource "google_project_iam_member" "deployer_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.github_actions_deployer.email}"

  depends_on = [google_service_account.github_actions_deployer]
}

# ============================================================================
# Workload Identity Pool for GitHub Actions (Keyless Authentication)
# ============================================================================

resource "google_iam_workload_identity_pool" "github_pool" {
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions Pool"
  description               = "Workload Identity Pool for GitHub Actions CI/CD"

  depends_on = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github_provider" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Provider"
  description                        = "OIDC provider for GitHub Actions"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Allow GitHub Actions to impersonate deployer service account
# NOTE: Update this with your GitHub username/repository
resource "google_service_account_iam_member" "github_workload_identity" {
  service_account_id = google_service_account.github_actions_deployer.name
  role               = "roles/iam.workloadIdentityUser"

  # TODO: Replace YOUR_GITHUB_USERNAME with your actual GitHub username
  member = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/YOUR_GITHUB_USERNAME/ntnl-churches-gcp"
}

# ============================================================================
# Outputs
# ============================================================================

output "bucket_name" {
  value       = google_storage_bucket.logs.name
  description = "Cloud Storage bucket for logs"
}

output "service_account_email" {
  value       = google_service_account.cloudrun_runtime.email
  description = "Service account email for Cloud Run runtime"
}

output "artifact_registry_url" {
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app.repository_id}"
  description = "Artifact Registry repository URL"
}

output "github_workload_identity_provider" {
  value       = google_iam_workload_identity_pool_provider.github_provider.name
  description = "Workload Identity Provider name for GitHub Actions"
}

output "github_service_account" {
  value       = google_service_account.github_actions_deployer.email
  description = "Service account for GitHub Actions deployment"
}

output "secrets_to_populate" {
  value = [
    "OPENAI_API_KEY",
    "PINECONE_API_KEY",
    "DISCORD_TOKEN",
    "CHATBOT_API_KEY"
  ]
  description = "Secret Manager secrets that need values populated"
}
