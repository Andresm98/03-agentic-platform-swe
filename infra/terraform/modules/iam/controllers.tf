# Políticas de mínimo privilegio de cada controlador (ADR-0002 §2).

data "aws_iam_policy_document" "ccm" {
  statement {
    sid       = "Describe"
    effect    = "Allow"
    actions   = ["ec2:DescribeInstances", "ec2:DescribeRegions", "ec2:DescribeAvailabilityZones", "ec2:DescribeTags"]
    resources = ["*"]
  }

  statement {
    sid       = "TagClusterInstances"
    effect    = "Allow"
    actions   = ["ec2:CreateTags"]
    resources = ["arn:${local.partition}:ec2:${local.region}:${local.account_id}:instance/*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/kubernetes.io/cluster/${var.cluster_name}"
      values   = ["owned"]
    }
  }
}

data "aws_iam_policy_document" "cluster_autoscaler" {
  # AWS no permite restringir los Describe* por recurso.
  statement {
    sid    = "Describe"
    effect = "Allow"
    actions = [
      "autoscaling:DescribeAutoScalingGroups",
      "autoscaling:DescribeAutoScalingInstances",
      "autoscaling:DescribeLaunchConfigurations",
      "autoscaling:DescribeScalingActivities",
      "autoscaling:DescribeTags",
      "ec2:DescribeImages",
      "ec2:DescribeInstanceTypes",
      "ec2:DescribeLaunchTemplateVersions",
      "ec2:GetInstanceTypesFromInstanceRequirements",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "MutateOnlyTaggedAsg"
    effect = "Allow"
    actions = [
      "autoscaling:SetDesiredCapacity",
      "autoscaling:TerminateInstanceInAutoScalingGroup",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/k8s.io/cluster-autoscaler/${var.cluster_name}"
      values   = ["owned"]
    }
  }
}

data "aws_iam_policy_document" "external_secrets" {
  statement {
    sid    = "ReadClusterSecrets"
    effect = "Allow"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
    ]
    # Cubre todas las rutas de CONTRACTS §6 (incluida la obligatoria langsmith-api-key).
    resources = [
      "${local.ssm_arn}${var.k8s_secrets_parameter_path}",
      "${local.ssm_arn}${var.k8s_secrets_parameter_path}/*",
    ]
  }

  statement {
    sid       = "DescribeParameters"
    effect    = "Allow"
    actions   = ["ssm:DescribeParameters"]
    resources = ["*"]
  }
}

locals {
  controller_policies = {
    ccm                = data.aws_iam_policy_document.ccm.json
    cluster_autoscaler = data.aws_iam_policy_document.cluster_autoscaler.json
    external_secrets   = data.aws_iam_policy_document.external_secrets.json
  }
}
