# Outputs surface useful results after apply (and are queryable via
# `terraform output`).

output "namespace" {
  description = "Namespace the app is deployed into."
  value       = kubernetes_namespace.app.metadata[0].name
}

output "release_name" {
  description = "Helm release name."
  value       = helm_release.app.name
}

output "release_status" {
  description = "Helm release status after apply."
  value       = helm_release.app.status
}

output "active_color" {
  description = "Blue-green color currently receiving production traffic."
  value       = var.active_color
}
