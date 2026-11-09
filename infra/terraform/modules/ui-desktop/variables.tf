variable "cluster_name" {
  description = "Nombre del cluster; prefijo de los recursos."
  type        = string
}

variable "vpc_id" {
  description = "VPC del laboratorio."
  type        = string
}

variable "subnet_id" {
  description = "Subred pública con salida a Internet para llegar a SSM."
  type        = string
}

variable "control_plane_security_group_id" {
  description = "SG del control plane, donde se abren los NodePort solo para este escritorio."
  type        = string
}

variable "control_plane_ip" {
  description = "IP privada fija del control plane."
  type        = string
}

variable "permissions_boundary_arn" {
  description = "Permissions boundary obligatoria de los roles agentic-*."
  type        = string
}

variable "password_parameter_name" {
  description = "Parámetro SSM donde la VM publica la contraseña de Administrator."
  type        = string
}

variable "github_repository" {
  description = "Repositorio del que se lee la lista de ejercicios publicados en la rama stage."
  type        = string
  default     = "Andresm98/03-agentic-platform-swe"
}

variable "instance_type" {
  description = "Tipo de instancia del escritorio."
  type        = string
  default     = "t3.medium"
}

variable "root_volume_size_gb" {
  description = "Tamaño del disco raíz."
  type        = number
  default     = 40
}

variable "argocd_nodeport" {
  description = "NodePort de Argo CD."
  type        = number
  default     = 30081
}

variable "dapr_nodeport" {
  description = "NodePort de Dapr Dashboard."
  type        = number
  default     = 30082
}

variable "nodeport_from" {
  description = "Primer puerto del rango abierto hacia el control plane."
  type        = number
  default     = 30081
}

variable "nodeport_to" {
  description = "Último puerto del rango abierto hacia el control plane."
  type        = number
  default     = 30082
}

variable "tags" {
  description = "Tags comunes del laboratorio."
  type        = map(string)
  default     = {}
}
