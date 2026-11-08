variable "cluster_name" {
  description = "Nombre del cluster (tags y nombre de la instancia)."
  type        = string
}

variable "ami_id" {
  description = "AMI de Ubuntu 24.04 amd64 fijada. Un cambio NO recrea el CP (ignore_changes) para no perder el datastore."
  type        = string

  validation {
    condition     = can(regex("^ami-[0-9a-f]{8,17}$", var.ami_id))
    error_message = "ami_id debe tener el formato ami-xxxxxxxx."
  }
}

variable "instance_type" {
  description = "Tipo de instancia del control plane."
  type        = string
  default     = "t3.large"

  validation {
    condition     = can(regex("^t3a?\\.", var.instance_type))
    error_message = "El CP usa la familia t3/t3a (cpu_credits=unlimited)."
  }
}

variable "subnet_id" {
  description = "Subnet donde vive el CP (debe contener private_ip)."
  type        = string
}

variable "private_ip" {
  description = "IP privada fija del CP; se pasa al user-data de los workers (no es un secreto)."
  type        = string
  default     = "10.0.1.10"

  validation {
    condition     = can(cidrhost("${var.private_ip}/32", 0))
    error_message = "private_ip debe ser una IPv4."
  }
}

variable "security_group_ids" {
  description = "SGs del control plane."
  type        = list(string)
}

variable "instance_profile_name" {
  description = "Instance profile agentic-cp-node."
  type        = string
}

variable "user_data" {
  description = "Script de user-data ya renderizado (server-userdata.sh.tftpl). Se comprime con gzip."
  type        = string
  sensitive   = false
}

variable "root_volume_size_gb" {
  description = "Tamaño del volumen raíz gp3."
  type        = number
  default     = 20

  validation {
    condition     = var.root_volume_size_gb >= 20 && var.root_volume_size_gb <= 50
    error_message = "Entre 20 y 50 GB (costo mínimo; el plan fija 20)."
  }
}

variable "join_token_parameter_name" {
  description = "Parámetro SSM (SecureString) donde el CP publica el join token."
  type        = string
  default     = "/agentic-platform/cluster/join-token"
}

variable "join_token_placeholder" {
  description = "Valor inicial del parámetro; los workers esperan hasta que el CP lo sustituya."
  type        = string
  default     = "pending-bootstrap"
}

variable "tags" {
  description = "Tags adicionales para la instancia y su volumen (las default_tags no llegan al volumen raíz)."
  type        = map(string)
  default     = {}
}
