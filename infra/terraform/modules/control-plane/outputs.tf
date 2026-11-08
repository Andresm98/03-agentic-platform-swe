output "instance_id" {
  description = "ID de la instancia del control plane (destino del túnel SSM)."
  value       = aws_instance.this.id
}

output "private_ip" {
  description = "IP privada fija del control plane."
  value       = aws_instance.this.private_ip
}

output "private_dns" {
  description = "Nombre DNS privado = nombre del nodo en Kubernetes."
  value       = aws_instance.this.private_dns
}

output "join_token_parameter_name" {
  description = "Parámetro SSM del join token (los workers lo esperan)."
  value       = aws_ssm_parameter.join_token.name
}
