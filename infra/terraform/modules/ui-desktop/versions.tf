terraform {
  required_version = ">= 1.11.0" # value_wo
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.72"
    }
  }
}
