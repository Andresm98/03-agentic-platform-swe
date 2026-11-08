output "role_arn" {
  description = "ARN que se configura en el datasource CloudWatch de Grafana Cloud (assumeRoleArn)."
  value       = aws_iam_role.grafana_cloudwatch.arn
}
