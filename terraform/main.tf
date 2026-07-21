# -------------------------------------------------------------------------- #
# The application environment, as code.
#
# (In cloud, a cluster module would go here first, e.g.:
#   module "eks" { source = "terraform-aws-modules/eks/aws" ... }
#  and the providers in providers.tf would point at module.eks outputs.)
# -------------------------------------------------------------------------- #

# The namespace, managed declaratively.
resource "kubernetes_namespace" "app" {
  metadata {
    name = var.namespace
    labels = {
      "app.kubernetes.io/part-of" = "cicd-demo"
      "managed-by"                = "terraform"
    }
  }
}

# The application itself, deployed as a Helm release from our local chart.
# Terraform drives Helm here, so `terraform plan` shows infra + app changes
# together, and `terraform destroy` tears the whole thing down.
resource "helm_release" "app" {
  name      = var.release_name
  namespace = kubernetes_namespace.app.metadata[0].name
  chart     = var.chart_path

  wait    = true
  timeout = 120

  # Map Terraform variables onto Helm chart values.
  set {
    name  = "replicaCount"
    value = var.replica_count
  }
  set {
    name  = "activeColor"
    value = var.active_color
  }
  set {
    name  = "previewColor"
    value = "green"
  }
  set {
    name  = "colors.blue.enabled"
    value = "true"
  }
  set {
    name  = "colors.blue.tag"
    value = var.blue_tag
  }
  set {
    name  = "colors.green.enabled"
    value = var.green_enabled
  }
  set {
    name  = "colors.green.tag"
    value = var.green_tag
  }
  set {
    name  = "vault.enabled"
    value = var.vault_enabled
  }
}
