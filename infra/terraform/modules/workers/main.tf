# Responsabilidad: launch template + ASG de los workers. El registro en el target
# group del NLB lo hace el módulo nlb (aws_autoscaling_traffic_source_attachment).

locals {
  name = "${var.cluster_name}-worker"

  instance_tags = merge(var.tags, {
    Name                                        = local.name
    "kubernetes.io/cluster/${var.cluster_name}" = "owned"
    "platform.io/role"                          = "worker"
  })

  # Tags del ASG: descubrimiento del CA + plantilla de labels para el scale-up.
  asg_tags = merge(
    local.instance_tags,
    {
      "k8s.io/cluster-autoscaler/enabled"             = "true"
      "k8s.io/cluster-autoscaler/${var.cluster_name}" = "owned"
    },
    { for k, v in var.node_labels : "k8s.io/cluster-autoscaler/node-template/label/${k}" => v },
  )
}

resource "aws_launch_template" "this" {
  name_prefix            = "${local.name}-"
  description            = "Workers K3s (agente)"
  image_id               = var.ami_id
  instance_type          = var.instance_type
  user_data              = base64gzip(var.user_data)
  vpc_security_group_ids = var.security_group_ids
  update_default_version = true
  ebs_optimized          = true

  iam_instance_profile {
    name = var.instance_profile_name
  }

  credit_specification {
    cpu_credits = "unlimited"
  }

  # IMDSv2 obligatorio; hop limit 1: los pods de apps no alcanzan las credenciales del nodo.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }

  monitoring {
    enabled = false
  }

  block_device_mappings {
    device_name = "/dev/sda1"
    ebs {
      volume_type           = "gp3"
      volume_size           = var.root_volume_size_gb
      encrypted             = true
      delete_on_termination = true
    }
  }

  dynamic "tag_specifications" {
    for_each = toset(["instance", "volume", "network-interface"])
    content {
      resource_type = tag_specifications.value
      tags          = local.instance_tags
    }
  }
}

resource "aws_autoscaling_group" "this" {
  name                      = local.name
  min_size                  = var.capacity.min
  desired_capacity          = var.capacity.desired
  max_size                  = var.capacity.max
  vpc_zone_identifier       = var.subnet_ids
  health_check_type         = "EC2"
  health_check_grace_period = 300
  default_cooldown          = 60
  capacity_rebalance        = false
  wait_for_capacity_timeout = "10m"

  # AWS no debe terminar nodos por su cuenta: solo el CA reduce capacidad.
  suspended_processes = ["AZRebalance"]

  # Métricas de grupo (sin costo): las lee el datasource CloudWatch de Grafana.
  enabled_metrics = [
    "GroupMinSize",
    "GroupMaxSize",
    "GroupDesiredCapacity",
    "GroupInServiceInstances",
    "GroupPendingInstances",
    "GroupTerminatingInstances",
    "GroupTotalInstances",
  ]
  metrics_granularity = "1Minute"

  launch_template {
    id      = aws_launch_template.this.id
    version = aws_launch_template.this.latest_version
  }

  dynamic "tag" {
    for_each = local.asg_tags
    content {
      key                 = tag.key
      value               = tag.value
      propagate_at_launch = true
    }
  }

  lifecycle {
    # El dueño de desired_capacity en ejecución es el Cluster Autoscaler (ADR-0001 §1).
    ignore_changes = [desired_capacity]
    # Sin instance_refresh: un refresh lanzaría una 4ª instancia (techo de 3 EC2).
  }
}
