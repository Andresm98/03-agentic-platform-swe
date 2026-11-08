# L-1 (ADR-0001 §1): dashboards y datasource CloudWatch de Grafana Cloud. Lo aplica observability.yml.

locals {
  dashboards_dir = "${path.module}/../dashboards"
  dashboards     = fileset(local.dashboards_dir, "*.json")
}

resource "grafana_folder" "agentic" {
  title = "Agentic Platform"
  uid   = "agentic-platform"
}

resource "grafana_dashboard" "this" {
  for_each = local.dashboards

  folder      = grafana_folder.agentic.uid
  config_json = file("${local.dashboards_dir}/${each.value}")
  overwrite   = true
}

# Consulta a demanda: sin metric streams ni scraping continuo (plan §1.3).
resource "grafana_data_source" "cloudwatch" {
  count = var.cloudwatch_role_arn != "" ? 1 : 0

  name = "agentic-cloudwatch"
  uid  = "agentic-cloudwatch"
  type = "cloudwatch"

  json_data_encoded = jsonencode({
    defaultRegion = var.aws_region
    authType      = "grafana_assume_role" # TODO(verify): modo de asunción de rol en el stack de Grafana Cloud
    assumeRoleArn = var.cloudwatch_role_arn
  })
}
