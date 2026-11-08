variable "role_name" {
  description = "Nombre determinista del rol (el datasource de Grafana Cloud lo referencia y sobrevive a destroy/apply)."
  type        = string
  default     = "agentic-grafana-cloudwatch"

  validation {
    condition     = startswith(var.role_name, "agentic-")
    error_message = "Los roles del proyecto llevan el prefijo agentic- (lo exige la política de Terraform)."
  }
}

variable "permissions_boundary_arn" {
  description = "ARN de agentic-boundary."
  type        = string
}

variable "grafana_cloud_aws_account_id" {
  description = "Cuenta AWS de Grafana Cloud que asume el rol (la indica Grafana Cloud al crear la conexión CloudWatch)."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.grafana_cloud_aws_account_id))
    error_message = "Debe ser un ID de cuenta AWS de 12 dígitos."
  }
}

variable "external_id" {
  description = "External ID que muestra Grafana Cloud para el datasource CloudWatch. No es un secreto, pero no se versiona: va en tfvars / variable del environment."
  type        = string

  validation {
    condition     = length(var.external_id) >= 8
    error_message = "external_id demasiado corto."
  }
}
