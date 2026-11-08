output "vpc_id" {
  description = "ID de la VPC del lab."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "Subnets públicas (una por AZ), en el orden de var.public_subnets. Las usan el ASG y el NLB."
  value       = aws_subnet.public[*].id
}

output "control_plane_subnet_id" {
  description = "Subnet de la primera AZ; contiene la IP privada fija del control plane."
  value       = aws_subnet.public[0].id
}

output "nlb_security_group_id" {
  description = "SG del NLB (TCP 80 desde allowed_cidrs)."
  value       = aws_security_group.nlb.id
}

output "control_plane_security_group_id" {
  description = "SG del control plane."
  value       = aws_security_group.control_plane.id
}

output "workers_security_group_id" {
  description = "SG de los workers (30080 solo desde el NLB)."
  value       = aws_security_group.workers.id
}
