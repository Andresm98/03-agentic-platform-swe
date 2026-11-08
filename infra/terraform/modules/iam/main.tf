# Responsabilidad: identidades IAM del cluster (ADR-0002 §2).
#
#   role/agentic-cp-node (instance profile CP): SSM core, PutParameter(join token), AssumeRole ↓
#     ├─ role/agentic-ccm                 ec2:Describe*, ec2:CreateTags
#     ├─ role/agentic-cluster-autoscaler  mutaciones condicionadas a la tag del ASG
#     └─ role/agentic-external-secrets    ssm:GetParameter(s) en /agentic-platform/k8s/*
#   role/agentic-worker-node (workers):   SSM core, GetParameter(join token)
#
# Los controladores usan AWS_CONFIG_FILE con role_arn + credential_source=Ec2InstanceMetadata,
# por eso su trust policy solo admite al rol del control plane.

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  partition  = data.aws_partition.current.partition
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region
  ssm_arn    = "arn:${local.partition}:ssm:${local.region}:${local.account_id}:parameter"

  join_token_arn = "${local.ssm_arn}${var.join_token_parameter_name}"
  ssm_core_arn   = "arn:${local.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"

  node_roles = {
    cp     = { name = "agentic-cp-node", description = "Instance profile del control plane K3s" }
    worker = { name = "agentic-worker-node", description = "Instance profile de los workers K3s" }
  }

  # Controladores que asume el CP. La política de cada uno está en controllers.tf.
  controller_roles = {
    ccm                = { name = "agentic-ccm", description = "AWS cloud-controller-manager (cloud-node, cloud-node-lifecycle)" }
    cluster_autoscaler = { name = "agentic-cluster-autoscaler", description = "Cluster Autoscaler (ASG por tags)" }
    external_secrets   = { name = "agentic-external-secrets", description = "External Secrets Operator (SSM Parameter Store)" }
  }
}

# --- Roles de nodo ------------------------------------------------------------------
data "aws_iam_policy_document" "ec2_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "node" {
  for_each = local.node_roles

  name                 = each.value.name
  description          = each.value.description
  assume_role_policy   = data.aws_iam_policy_document.ec2_trust.json
  permissions_boundary = var.permissions_boundary_arn
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  for_each = local.node_roles

  role       = aws_iam_role.node[each.key].name
  policy_arn = local.ssm_core_arn
}

resource "aws_iam_instance_profile" "node" {
  for_each = local.node_roles

  name = each.value.name
  role = aws_iam_role.node[each.key].name
}

data "aws_iam_policy_document" "cp_node" {
  statement {
    sid       = "PublishJoinToken"
    effect    = "Allow"
    actions   = ["ssm:PutParameter", "ssm:GetParameter"]
    resources = [local.join_token_arn]
  }

  statement {
    sid       = "AssumeControllerRoles"
    effect    = "Allow"
    actions   = ["sts:AssumeRole"]
    resources = [for r in aws_iam_role.controller : r.arn]
  }
}

resource "aws_iam_role_policy" "cp_node" {
  name   = "cp-node"
  role   = aws_iam_role.node["cp"].id
  policy = data.aws_iam_policy_document.cp_node.json
}

data "aws_iam_policy_document" "worker_node" {
  statement {
    sid       = "ReadJoinToken"
    effect    = "Allow"
    actions   = ["ssm:GetParameter"]
    resources = [local.join_token_arn]
  }
}

resource "aws_iam_role_policy" "worker_node" {
  name   = "worker-node"
  role   = aws_iam_role.node["worker"].id
  policy = data.aws_iam_policy_document.worker_node.json
}

# --- Roles de controlador ------------------------------------------------------------
data "aws_iam_policy_document" "controller_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.node["cp"].arn]
    }
  }
}

resource "aws_iam_role" "controller" {
  for_each = local.controller_roles

  name                 = each.value.name
  description          = each.value.description
  assume_role_policy   = data.aws_iam_policy_document.controller_trust.json
  permissions_boundary = var.permissions_boundary_arn
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "controller" {
  for_each = local.controller_roles

  name   = each.key
  role   = aws_iam_role.controller[each.key].id
  policy = local.controller_policies[each.key]
}
