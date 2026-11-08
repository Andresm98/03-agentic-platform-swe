variable "region" {
  description = "Región AWS del proyecto."
  type        = string
  default     = "us-east-1"
}

variable "owner" {
  description = "Valor de la tag Owner (persona o equipo responsable)."
  type        = string
}

variable "budget_limit_usd" {
  description = "Límite mensual del AWS Budget en USD."
  type        = number
  default     = 10
}

variable "budget_alert_emails" {
  description = "Correos que reciben las alertas del Budget. Sin valor por defecto: no se publican correos reales en Git."
  type        = list(string)

  validation {
    condition     = length(var.budget_alert_emails) > 0
    error_message = "Indica al menos un correo para las alertas del Budget."
  }
}

variable "github_repository" {
  description = "Repositorio <owner>/<repo> de GitHub autorizado a asumir los roles vía OIDC."
  type        = string
  default     = "Andresm98/03-agentic-platform-swe"
}

variable "github_oidc_subject_prefix" {
  description = <<-EOT
    Prefijo del sub OIDC que emite GitHub, antes de ":environment:<nombre>". Este repositorio usa el formato
    inmutable, con los ID del propietario y del repositorio. Se consulta con:
    gh api repos/<owner>/<repo>/actions/oidc/customization/sub --jq .sub_claim_prefix
  EOT
  type        = string
  default     = "repo:Andresm98@41342993/03-agentic-platform-swe@1449959239"
}

variable "github_lab_environment" {
  description = "Environment de GitHub (con aprobación) que puede asumir role/agentic-github-actions."
  type        = string
  default     = "lab"
}

variable "github_reaper_environment" {
  description = <<-EOT
    Environment de GitHub SIN revisores que usa lab-reaper.yml (cron). Asume role/agentic-github-reaper,
    que solo puede destruir. Vacío = no se crea el rol del reaper (lab-reaper.yml usará el environment lab
    y quedará esperando aprobación en cada ejecución).
  EOT
  type        = string
  default     = "lab-reaper"
}

variable "github_observability_environment" {
  description = "Environment de GitHub de observability.yml. Asume role/agentic-github-observability (solo estado S3 de observability/). Vacío = no se crea."
  type        = string
  default     = "observability"
}

variable "state_bucket_name" {
  description = "Nombre del bucket de estado. Vacío = agentic-platform-tfstate-<account_id>."
  type        = string
  default     = ""
}
