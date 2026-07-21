# Input variables — the knobs for this infrastructure. Override via a
# terraform.tfvars file, -var flags, or TF_VAR_* environment variables.

variable "kubeconfig_path" {
  description = "Path to the kubeconfig file."
  type        = string
  default     = "~/.kube/config"
}

variable "kube_context" {
  description = "kubeconfig context to target (kind prefixes clusters with 'kind-')."
  type        = string
  default     = "kind-cicd"
}

variable "namespace" {
  description = "Namespace to deploy the app into."
  type        = string
  default     = "cicd-demo"
}

variable "release_name" {
  description = "Helm release name."
  type        = string
  default     = "cicd-demo"
}

variable "chart_path" {
  description = "Path to the local Helm chart (relative to this module)."
  type        = string
  default     = "../helm/cicd-demo"
}

variable "replica_count" {
  description = "Replicas per color track."
  type        = number
  default     = 2
}

variable "active_color" {
  description = "Blue-green: which color the main Service routes to."
  type        = string
  default     = "blue"

  validation {
    condition     = contains(["blue", "green"], var.active_color)
    error_message = "active_color must be either 'blue' or 'green'."
  }
}

variable "blue_tag" {
  description = "Image tag for the blue track."
  type        = string
  default     = "1.0.3"
}

variable "green_enabled" {
  description = "Whether the green track is deployed."
  type        = bool
  default     = true
}

variable "green_tag" {
  description = "Image tag for the green track."
  type        = string
  default     = "1.0.4"
}
