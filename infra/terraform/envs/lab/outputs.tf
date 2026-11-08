output "nlb_dns_name" {
  description = "URL pública de la demo: http://<nlb_dns_name>/"
  value       = module.nlb.dns_name
}

output "target_group_arn" {
  description = "Target group del NLB (demo 09)."
  value       = module.nlb.target_group_arn
}

output "asg_name" {
  description = "ASG de workers (demos 07, 08 y 11)."
  value       = module.workers.asg_name
}

output "control_plane_instance_id" {
  description = "Destino del túnel SSM (infra/scripts/tunnel.sh)."
  value       = module.control_plane.instance_id
}

output "control_plane_private_dns" {
  description = "Nombre del nodo del control plane en Kubernetes."
  value       = module.control_plane.private_dns
}

output "vpc_id" {
  description = "VPC del lab (cost-check.sh)."
  value       = module.network.vpc_id
}

output "grafana_cloudwatch_role_arn" {
  description = "Rol del datasource CloudWatch de Grafana Cloud (vacío si no se creó)."
  value       = try(module.observability_aws[0].role_arn, "")
}

output "created_at" {
  description = "Marca temporal del alta (tag CreatedAt de la VPC; la usa lab-reaper)."
  value       = time_static.created_at.rfc3339
}
