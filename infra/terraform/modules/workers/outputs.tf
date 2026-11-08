output "asg_name" {
  description = "Nombre del ASG (lo descubre el CA por tags; lo usan el NLB y los scripts de demo)."
  value       = aws_autoscaling_group.this.name
}

output "asg_arn" {
  description = "ARN del ASG."
  value       = aws_autoscaling_group.this.arn
}

output "launch_template_id" {
  description = "ID del launch template de los workers."
  value       = aws_launch_template.this.id
}
