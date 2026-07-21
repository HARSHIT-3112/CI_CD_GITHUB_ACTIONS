# Providers are how Terraform talks to real APIs. Here both providers target the
# local kind cluster via your kubeconfig context (kind-cicd).
#
# In a CLOUD setup you would instead provision the cluster with a module such as
# `terraform-aws-modules/eks/aws` (or google's GKE module) in THIS same config,
# and point these providers at that cluster's endpoint/credentials — the app
# layer below (namespace + helm_release) would stay exactly the same.

provider "kubernetes" {
  config_path    = var.kubeconfig_path
  config_context = var.kube_context
}

provider "helm" {
  kubernetes {
    config_path    = var.kubeconfig_path
    config_context = var.kube_context
  }
}
