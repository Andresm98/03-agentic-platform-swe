# Responsabilidad: la instancia del control plane K3s y el parámetro del join token.

locals {
  name = "${var.cluster_name}-control-plane"
  tags = merge(var.tags, {
    Name                                        = local.name
    "kubernetes.io/cluster/${var.cluster_name}" = "owned"
    "platform.io/role"                          = "control-plane"
  })
}

# El CP escribe el valor real al arrancar (aws ssm put-parameter --overwrite).
# Terraform crea el recurso para que su ciclo de vida siga al lab. El marcador se escribe con
# `value_wo` (solo escritura): al refrescar, el provider deja `value` a null, así que el token
# real que escribe el control plane nunca llega al estado (plan §1.1 #7). `ignore_changes` no
# basta: solo evita el diff, y el refresh guardaría el token en el estado.
resource "aws_ssm_parameter" "join_token" {
  name             = var.join_token_parameter_name
  description      = "Join token de K3s (lo escribe el control plane)."
  type             = "SecureString"
  value_wo         = var.join_token_placeholder
  value_wo_version = 1
}

resource "aws_instance" "this" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  private_ip             = var.private_ip
  vpc_security_group_ids = var.security_group_ids
  iam_instance_profile   = var.instance_profile_name
  user_data_base64       = base64gzip(var.user_data)
  monitoring             = false # sin detailed monitoring (costo)
  ebs_optimized          = true

  credit_specification {
    cpu_credits = "unlimited"
  }

  # IMDSv2 obligatorio; hop limit 2 para que los pods del CCM, CA y ESO lleguen a IMDS.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
    instance_metadata_tags      = "disabled"
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size_gb
    encrypted             = true
    delete_on_termination = true
    tags                  = local.tags
  }

  tags = local.tags

  # Un cambio de AMI o de user-data recrearía el CP y se perdería el datastore
  # (single-CP, sin HA). Para aplicar cambios: destroy + up del lab completo.
  lifecycle {
    ignore_changes = [ami, user_data, user_data_base64]
  }

  depends_on = [aws_ssm_parameter.join_token]
}
