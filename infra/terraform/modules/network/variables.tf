variable "cluster_name" {
  description = "Nombre del cluster (tag kubernetes.io/cluster/<name> y prefijo de nombres)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]{3,32}$", var.cluster_name))
    error_message = "cluster_name: 3-32 caracteres [a-z0-9-]."
  }
}

variable "vpc_cidr" {
  description = "CIDR de la VPC."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr debe ser un CIDR IPv4 válido."
  }
}

variable "public_subnets" {
  description = "Subnets públicas, una por AZ. La primera aloja el control plane (IP fija)."
  type = list(object({
    az   = string
    cidr = string
  }))

  validation {
    condition     = length(var.public_subnets) >= 2
    error_message = "El NLB y el ASG necesitan al menos 2 subnets en AZ distintas."
  }

  validation {
    condition     = length(distinct([for s in var.public_subnets : s.az])) == length(var.public_subnets)
    error_message = "Cada subnet debe estar en una AZ distinta."
  }
}

variable "allowed_cidrs" {
  description = "CIDRs que pueden llegar al NLB por TCP 80 (demo pública: 0.0.0.0/0)."
  type        = list(string)
  default     = ["0.0.0.0/0"]

  validation {
    condition     = alltrue([for c in var.allowed_cidrs : can(cidrhost(c, 0))])
    error_message = "allowed_cidrs solo admite CIDRs IPv4 válidos."
  }
}

variable "created_at" {
  description = "Marca temporal RFC3339 del alta del lab. Se pone como tag CreatedAt en la VPC; la lee lab-reaper."
  type        = string

  validation {
    condition     = can(formatdate("YYYY", var.created_at))
    error_message = "created_at debe ser una fecha RFC3339."
  }
}
