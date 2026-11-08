variable "cluster_name" {
  description = "Nombre del cluster; valor de la tag k8s.io/cluster-autoscaler/<name>."
  type        = string
}

variable "permissions_boundary_arn" {
  description = "ARN de agentic-boundary (output de infra/terraform/bootstrap). Obligatoria en todos los roles."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:policy/agentic-boundary$", var.permissions_boundary_arn))
    error_message = "permissions_boundary_arn debe ser el ARN de la política agentic-boundary."
  }
}

variable "join_token_parameter_name" {
  description = "Nombre del parámetro SSM del join token de K3s."
  type        = string
  default     = "/agentic-platform/cluster/join-token"

  validation {
    condition     = startswith(var.join_token_parameter_name, "/agentic-platform/cluster/")
    error_message = "El join token debe vivir bajo /agentic-platform/cluster/ (lo exige la política de Terraform)."
  }
}

variable "k8s_secrets_parameter_path" {
  description = "Prefijo SSM de los secretos que lee External Secrets (CONTRACTS §6)."
  type        = string
  default     = "/agentic-platform/k8s"

  validation {
    condition     = startswith(var.k8s_secrets_parameter_path, "/") && !endswith(var.k8s_secrets_parameter_path, "/")
    error_message = "Ruta absoluta sin barra final, p. ej. /agentic-platform/k8s."
  }
}
