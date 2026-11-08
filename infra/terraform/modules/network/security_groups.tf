# Reglas de IMPLEMENTATION_PLAN §2.1. Sin SSH ni 6443 públicos: acceso por Session Manager.
# Los tres SG viven juntos porque se referencian entre sí (NLB -> workers -> CP).

resource "aws_security_group" "nlb" {
  name        = "${var.cluster_name}-nlb"
  description = "NLB publico: TCP 80 desde allowed_cidrs"
  vpc_id      = aws_vpc.this.id
  tags        = merge(local.cluster_tag, { Name = "${var.cluster_name}-nlb" })
}

resource "aws_security_group" "control_plane" {
  name        = "${var.cluster_name}-control-plane"
  description = "Control plane K3s"
  vpc_id      = aws_vpc.this.id
  tags        = merge(local.cluster_tag, { Name = "${var.cluster_name}-control-plane" })
}

resource "aws_security_group" "workers" {
  name        = "${var.cluster_name}-workers"
  description = "Workers K3s"
  vpc_id      = aws_vpc.this.id
  tags        = merge(local.cluster_tag, { Name = "${var.cluster_name}-workers" })
}

locals {
  node_sgs = {
    cp      = aws_security_group.control_plane.id
    workers = aws_security_group.workers.id
  }

  # Todas las combinaciones destino <- origen entre nodos (cp/workers).
  node_pairs = {
    for pair in setproduct(keys(local.node_sgs), keys(local.node_sgs)) :
    "${pair[0]}-from-${pair[1]}" => { dst = local.node_sgs[pair[0]], src = local.node_sgs[pair[1]] }
  }

  node_to_node_ports = {
    vxlan   = { protocol = "udp", port = 8472, description = "Flannel VXLAN" }
    kubelet = { protocol = "tcp", port = 10250, description = "kubelet (metrics-server, logs, exec)" }
    # node-exporter usa hostNetwork: Alloy (CP) lo raspa por la IP del nodo, sin VXLAN.
    node_exporter = { protocol = "tcp", port = 9100, description = "node-exporter (scraping de Alloy)" }
  }

  node_rules = {
    for item in setproduct(keys(local.node_pairs), keys(local.node_to_node_ports)) :
    "${item[1]}-${item[0]}" => merge(local.node_pairs[item[0]], local.node_to_node_ports[item[1]])
  }

  # Salida hacia Internet: 443 (SSM, GitHub/GHCR, registry.k8s.io, quay.io, Grafana
  # Cloud, AWS APIs) y 80 (repos apt de Ubuntu). DNS (169.254.169.253) y NTP de
  # Amazon no pasan por los SG.
  internet_egress = { https = 443, http = 80 }

  node_egress = {
    for item in setproduct(keys(local.node_sgs), keys(local.internet_egress)) :
    "${item[0]}-${item[1]}" => { sg = local.node_sgs[item[0]], port = local.internet_egress[item[1]] }
  }
}

# --- NLB -----------------------------------------------------------------------
resource "aws_vpc_security_group_ingress_rule" "nlb_http" {
  for_each = toset(var.allowed_cidrs)

  security_group_id = aws_security_group.nlb.id
  description       = "Demo publica HTTP"
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_egress_rule" "nlb_to_workers" {
  security_group_id            = aws_security_group.nlb.id
  description                  = "NodePort de Traefik (trafico y health check)"
  referenced_security_group_id = aws_security_group.workers.id
  ip_protocol                  = "tcp"
  from_port                    = 30080
  to_port                      = 30080
}

# --- Workers ---------------------------------------------------------------------
resource "aws_vpc_security_group_ingress_rule" "workers_from_nlb" {
  security_group_id            = aws_security_group.workers.id
  description                  = "NodePort 30080 solo desde el NLB"
  referenced_security_group_id = aws_security_group.nlb.id
  ip_protocol                  = "tcp"
  from_port                    = 30080
  to_port                      = 30080
}

# --- Control plane: API de K3s desde workers (sin 9345: no hay supervisor HA) ------
resource "aws_vpc_security_group_ingress_rule" "cp_api_from_workers" {
  security_group_id            = aws_security_group.control_plane.id
  description                  = "API de K3s desde workers"
  referenced_security_group_id = aws_security_group.workers.id
  ip_protocol                  = "tcp"
  from_port                    = 6443
  to_port                      = 6443
}

# --- Nodos <-> nodos ---------------------------------------------------------------
resource "aws_vpc_security_group_ingress_rule" "node_to_node" {
  for_each = local.node_rules

  security_group_id            = each.value.dst
  description                  = each.value.description
  referenced_security_group_id = each.value.src
  ip_protocol                  = each.value.protocol
  from_port                    = each.value.port
  to_port                      = each.value.port
}

# --- Salida ------------------------------------------------------------------------
resource "aws_vpc_security_group_egress_rule" "internet" {
  for_each = local.node_egress

  security_group_id = each.value.sg
  description       = "Salida a Internet TCP ${each.value.port}"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = each.value.port
  to_port           = each.value.port
}

resource "aws_vpc_security_group_egress_rule" "intra_vpc" {
  for_each = local.node_sgs

  security_group_id = each.value
  description       = "Trafico entre nodos dentro de la VPC"
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "-1"
}
