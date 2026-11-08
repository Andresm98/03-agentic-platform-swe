output "cp_instance_profile_name" {
  description = "Instance profile del control plane (agentic-cp-node)."
  value       = aws_iam_instance_profile.node["cp"].name
}

output "worker_instance_profile_name" {
  description = "Instance profile de los workers (agentic-worker-node)."
  value       = aws_iam_instance_profile.node["worker"].name
}

output "cp_role_arn" {
  description = "ARN de role/agentic-cp-node."
  value       = aws_iam_role.node["cp"].arn
}

output "controller_role_arns" {
  description = "ARN de los roles de controlador, por clave: ccm, cluster_autoscaler, external_secrets. Se inyectan en los ConfigMaps AWS_CONFIG_FILE del bootstrap."
  value       = { for k, r in aws_iam_role.controller : k => r.arn }
}

output "join_token_parameter_arn" {
  description = "ARN del parámetro SSM del join token."
  value       = local.join_token_arn
}
