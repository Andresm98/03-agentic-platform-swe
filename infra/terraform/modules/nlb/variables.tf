variable "cluster_name" {
  description = "Prefijo de nombres (máx. 32 caracteres en total para NLB/TG)."
  type        = string

  validation {
    condition     = length(var.cluster_name) <= 26
    error_message = "cluster_name <= 26 caracteres para que '<name>-nlb' y '<name>-web' quepan en 32."
  }
}

variable "vpc_id" {
  description = "VPC del target group."
  type        = string
}

variable "subnet_ids" {
  description = "Subnets públicas del NLB (una por AZ)."
  type        = list(string)
}

variable "security_group_ids" {
  description = "SGs del NLB (TCP 80 desde allowed_cidrs)."
  type        = list(string)
}

variable "asg_name" {
  description = "ASG de workers que se registra como traffic source del target group."
  type        = string
}

variable "node_port" {
  description = "NodePort de Traefik (entrypoint web)."
  type        = number
  default     = 30080

  validation {
    condition     = var.node_port >= 30000 && var.node_port <= 32767
    error_message = "node_port debe estar en el rango NodePort (30000-32767)."
  }
}

variable "health_check_path" {
  description = "Ruta del health check HTTP, servida por Traefik (ping en el entrypoint web)."
  type        = string
  default     = "/ping"
}

variable "deregistration_delay_seconds" {
  description = "Deregistration delay del target group (scale-down rápido)."
  type        = number
  default     = 30
}
