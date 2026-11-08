# Responsabilidad: red del lab (VPC, subnets públicas, IGW, rutas). Sin NAT ni EIP
# (ADR-0001 §5). Los Security Groups están en security_groups.tf.

locals {
  cluster_tag = { "kubernetes.io/cluster/${var.cluster_name}" = "owned" }
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true # nombres ip-10-0-x-y.ec2.internal (nombre de nodo, ADR-0002 §1)

  tags = merge(local.cluster_tag, {
    Name      = "${var.cluster_name}-vpc"
    CreatedAt = var.created_at
  })
}

# Sin reglas: neutraliza el SG por defecto de la VPC.
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.cluster_name}-default-closed" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.cluster_name}-igw" }
}

# Subnets públicas sin NAT (costo): los nodos salen con IP pública propia, pero
# los SG no admiten tráfico entrante de Internet salvo hacia el NLB.
resource "aws_subnet" "public" {
  count = length(var.public_subnets)

  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnets[count.index].cidr
  availability_zone       = var.public_subnets[count.index].az
  map_public_ip_on_launch = true #checkov:skip=CKV_AWS_130:sin NAT por costo (ADR-0001 §5); entrada cerrada por SG

  tags = merge(local.cluster_tag, {
    Name                     = "${var.cluster_name}-public-${var.public_subnets[count.index].az}"
    "kubernetes.io/role/elb" = "1"
  })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.cluster_name}-public" }
}

resource "aws_route" "internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}
