output "dns_name" {
  description = "DNS público del NLB (URL de la demo: http://<dns_name>/)."
  value       = aws_lb.this.dns_name
}

output "nlb_arn" {
  description = "ARN del NLB."
  value       = aws_lb.this.arn
}

output "target_group_arn" {
  description = "ARN del target group (describe-target-health en la demo 09)."
  value       = aws_lb_target_group.web.arn
}
