output "instance_id" {
  description = "ID de la VM para conectarse desde Fleet Manager."
  value       = aws_instance.this.id
}
