variable "cluster_name" {
  description = "Nombre del cluster (tags del CA y del CCM)."
  type        = string
}

variable "ami_id" {
  description = "AMI de Ubuntu 24.04 amd64 fijada."
  type        = string

  validation {
    condition     = can(regex("^ami-[0-9a-f]{8,17}$", var.ami_id))
    error_message = "ami_id debe tener el formato ami-xxxxxxxx."
  }
}

variable "instance_type" {
  description = "Tipo de instancia de los workers."
  type        = string
  default     = "t3.medium"

  validation {
    condition     = can(regex("^t3a?\\.", var.instance_type))
    error_message = "Los workers usan la familia t3/t3a (cpu_credits=unlimited)."
  }
}

variable "subnet_ids" {
  description = "Subnets del ASG (una por AZ)."
  type        = list(string)

  validation {
    condition     = length(var.subnet_ids) >= 2
    error_message = "El ASG necesita al menos 2 subnets."
  }
}

variable "security_group_ids" {
  description = "SGs de los workers."
  type        = list(string)
}

variable "instance_profile_name" {
  description = "Instance profile agentic-worker-node."
  type        = string
}

variable "user_data" {
  description = "Script de user-data ya renderizado (agent-userdata.sh.tftpl). Se comprime con gzip."
  type        = string
}

variable "capacity" {
  description = "Capacidad del ASG. desired solo se usa al crear: después su dueño es el Cluster Autoscaler."
  type = object({
    min     = number
    desired = number
    max     = number
  })
  default = { min = 1, desired = 1, max = 2 }

  validation {
    condition     = var.capacity.min <= var.capacity.desired && var.capacity.desired <= var.capacity.max && var.capacity.max <= 2
    error_message = "Debe cumplirse min <= desired <= max <= 2 (techo de 3 EC2 contando el CP)."
  }
}

variable "root_volume_size_gb" {
  description = "Tamaño del volumen raíz gp3."
  type        = number
  default     = 20

  validation {
    condition     = var.root_volume_size_gb >= 20 && var.root_volume_size_gb <= 50
    error_message = "Entre 20 y 50 GB."
  }
}

variable "node_labels" {
  description = "Labels de nodo que el CA debe conocer para simular un nodo nuevo (tags node-template)."
  type        = map(string)
  default     = { "platform.io/pool" = "apps", "platform.io/role" = "worker" }
}

variable "tags" {
  description = "Tags comunes (Project, Lifecycle, Owner). Se propagan a instancias y volúmenes vía launch template."
  type        = map(string)
  default     = {}
}
