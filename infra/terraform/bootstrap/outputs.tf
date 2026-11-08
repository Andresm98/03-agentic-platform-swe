output "state_bucket" {
  description = "Bucket del estado remoto (backend-config bucket=...)."
  value       = aws_s3_bucket.state.id
}

output "permissions_boundary_arn" {
  description = "ARN de agentic-boundary (variable permissions_boundary_arn de envs/lab)."
  value       = aws_iam_policy.boundary.arn
}

output "github_role_arns" {
  description = "Roles de GitHub Actions. Copiar a las variables de cada environment (AWS_ROLE_ARN)."
  value       = { for k, r in aws_iam_role.github : k => r.arn }
}

output "oidc_subjects" {
  description = "sub exactos aceptados por cada rol."
  value       = { for k, env in local.github_roles : k => "repo:${var.github_repository}:environment:${env}" }
}
