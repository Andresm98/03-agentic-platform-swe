variable "region" {
  description = "Región AWS (CONTRACTS §2)."
  type        = string
  default     = "us-east-1"

  validation {
    condition     = var.region == "us-east-1"
    error_message = "El backend, la boundary y los values de GitOps asumen us-east-1."
  }
}

variable "owner" {
  description = "Valor de la tag obligatoria Owner."
  type        = string

  validation {
    condition     = length(trimspace(var.owner)) > 0
    error_message = "owner no puede estar vacío."
  }
}

variable "cluster_name" {
  description = "Nombre del cluster (tags del CCM y del CA). Debe coincidir con gitops/platform."
  type        = string
  default     = "agentic-platform"
}

variable "ami_id" {
  description = "AMI de Ubuntu 24.04 LTS amd64 (hvm, gp3) resuelta una vez y fijada. Ver terraform.tfvars.example."
  type        = string
}

variable "permissions_boundary_arn" {
  description = "ARN de agentic-boundary (output permissions_boundary_arn de bootstrap)."
  type        = string
}

variable "allowed_cidrs" {
  description = "CIDRs con acceso al NLB :80. La demo es pública."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "control_plane_instance_type" {
  description = "Tipo de instancia del control plane."
  type        = string
  default     = "t3.large"
}

variable "worker_instance_type" {
  description = "Tipo de instancia de los workers."
  type        = string
  default     = "t3.medium"
}

variable "grafana_cloud_aws_account_id" {
  description = "Cuenta AWS de Grafana Cloud para el datasource CloudWatch. Vacío = no se crea el rol."
  type        = string
  default     = ""
}

variable "grafana_cloudwatch_external_id" {
  description = "External ID del datasource CloudWatch de Grafana Cloud. Llega por tfvars o TF_VAR_ y no se versiona."
  type        = string
  default     = ""
}
