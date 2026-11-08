terraform {
  required_version = ">= 1.10.0"

  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "~> 4.53"
    }
  }

  # Configuración parcial: el bucket llega por -backend-config (observability.yml).
  backend "s3" {
    key          = "observability/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}

# URL y token por entorno (GRAFANA_URL, GRAFANA_AUTH): nunca en ficheros.
provider "grafana" {}
