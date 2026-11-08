variable "cloudwatch_role_arn" {
  description = "ARN determinista de role/agentic-grafana-cloudwatch. Vacío = no se crea el datasource."
  type        = string
  default     = ""

  validation {
    condition     = var.cloudwatch_role_arn == "" || can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:role/agentic-grafana-cloudwatch$", var.cloudwatch_role_arn))
    error_message = "Debe ser el ARN de role/agentic-grafana-cloudwatch."
  }
}

variable "aws_region" {
  description = "Región por defecto del datasource CloudWatch."
  type        = string
  default     = "us-east-1"
}
