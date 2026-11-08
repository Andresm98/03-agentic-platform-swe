# Responsabilidad: rol cross-account para el datasource CloudWatch de Grafana Cloud
# (plan §1.3 y Fase I). Solo lectura de métricas; sin metric streams ni Container Insights.

data "aws_iam_policy_document" "trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${var.grafana_cloud_aws_account_id}:root"]
    }
    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.external_id]
    }
  }
}

resource "aws_iam_role" "grafana_cloudwatch" {
  name                 = var.role_name
  description          = "Grafana Cloud: datasource CloudWatch (solo lectura de métricas)."
  assume_role_policy   = data.aws_iam_policy_document.trust.json
  permissions_boundary = var.permissions_boundary_arn
  max_session_duration = 3600
}

data "aws_iam_policy_document" "read_metrics" {
  statement {
    sid    = "ReadMetrics"
    effect = "Allow"
    actions = [
      "cloudwatch:DescribeAlarmsForMetric",
      "cloudwatch:DescribeAlarmHistory",
      "cloudwatch:DescribeAlarms",
      "cloudwatch:ListMetrics",
      "cloudwatch:GetMetricData",
      "cloudwatch:GetInsightRuleReport",
      "ec2:DescribeTags",
      "ec2:DescribeInstances",
      "ec2:DescribeRegions",
      "tag:GetResources",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "read_metrics" {
  name   = "read-cloudwatch-metrics"
  role   = aws_iam_role.grafana_cloudwatch.id
  policy = data.aws_iam_policy_document.read_metrics.json
}
