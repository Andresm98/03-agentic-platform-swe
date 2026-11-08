# Responsabilidad: exposición pública (ADR-0002 §4). NLB :80 -> TG instance :30080
# -> Traefik (DaemonSet, externalTrafficPolicy Local). El service controller del CCM
# está desactivado: este NLB es solo de Terraform.

resource "aws_lb" "this" {
  name                             = "${var.cluster_name}-nlb"
  load_balancer_type               = "network"
  internal                         = false #checkov:skip=CKV_AWS_150:demo pública efímera; sin protección de borrado para garantizar el destroy
  subnets                          = var.subnet_ids
  security_groups                  = var.security_group_ids
  enable_cross_zone_load_balancing = true
  enable_deletion_protection       = false
  ip_address_type                  = "ipv4"
}

resource "aws_lb_target_group" "web" {
  name                 = "${var.cluster_name}-web"
  port                 = var.node_port
  protocol             = "TCP"
  target_type          = "instance"
  vpc_id               = var.vpc_id
  deregistration_delay = var.deregistration_delay_seconds
  preserve_client_ip   = "true" # el rate limit de Traefik es por IP de cliente

  health_check {
    enabled             = true
    protocol            = "HTTP"
    port                = "traffic-port"
    path                = var.health_check_path
    matcher             = "200"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "TCP" #checkov:skip=CKV_AWS_2:sin dominio ni TLS en la demo (IMPLEMENTATION_PLAN §8)

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

# El ASG registra/deregistra sus instancias en el TG (no se usa target_group_arns
# en el ASG para que haya un único dueño de la asociación).
resource "aws_autoscaling_traffic_source_attachment" "web" {
  autoscaling_group_name = var.asg_name

  traffic_source {
    identifier = aws_lb_target_group.web.arn
    type       = "elbv2"
  }
}
