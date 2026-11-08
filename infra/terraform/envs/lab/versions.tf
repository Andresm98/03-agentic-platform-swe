terraform {
  required_version = ">= 1.11.0" # use_lockfile en el backend S3

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.72"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.14"
    }
  }

  # Configuración parcial: el bucket llega por -backend-config (ver backend.hcl.example).
  backend "s3" {
    key          = "lab/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = local.common_tags
  }
}
