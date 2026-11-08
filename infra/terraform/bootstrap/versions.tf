# Capa L-1 (persistente). Se aplica una sola vez desde local con credenciales de
# administrador (infra/scripts/bootstrap.sh). Su estado es local a propósito: es el
# stack que crea el bucket del estado remoto (huevo y gallina). El .tfstate está en
# .gitignore; guárdalo fuera de Git (p. ej. en un gestor de contraseñas) o reimporta.
terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.72"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "agentic-platform"
      Lifecycle = "persistent"
      Owner     = var.owner
      ManagedBy = "terraform/bootstrap"
    }
  }
}
