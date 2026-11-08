# -----------------------------------------------------------------------------
# Permissions boundary agentic-boundary
#
# Techo de permisos de TODOS los roles agentic-* que crea Terraform (bootstrap y lab).
# role/agentic-github-actions solo puede crear roles que la lleven (condición
# iam:PermissionsBoundary), así que nunca puede fabricar un rol más poderoso que ella.
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "boundary" {
  statement {
    sid    = "LabInfrastructure"
    effect = "Allow"
    actions = [
      "ec2:*",
      "elasticloadbalancing:*",
      "autoscaling:*",
      "cloudwatch:Describe*",
      "cloudwatch:Get*",
      "cloudwatch:List*",
      "tag:GetResources",
      "sts:GetCallerIdentity",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.region]
    }
  }

  statement {
    sid       = "GlobalReadOnly"
    effect    = "Allow"
    actions   = ["cloudwatch:GetMetricData", "cloudwatch:ListMetrics", "ec2:DescribeRegions", "sts:GetCallerIdentity"]
    resources = ["*"]
  }

  statement {
    sid    = "SsmAgentAndParameters"
    effect = "Allow"
    actions = [
      "ssm:*",
      "ssmmessages:*",
      "ec2messages:*",
    ]
    resources = ["*"]
  }

  statement {
    sid     = "TerraformState"
    effect  = "Allow"
    actions = ["s3:ListBucket", "s3:GetBucketLocation", "s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:GetEncryptionConfiguration"]
    resources = [
      aws_s3_bucket.state.arn,
      "${aws_s3_bucket.state.arn}/*",
    ]
  }

  statement {
    sid    = "ProjectIam"
    effect = "Allow"
    actions = [
      "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:TagRole", "iam:UntagRole",
      "iam:UpdateRole", "iam:UpdateRoleDescription", "iam:UpdateAssumeRolePolicy",
      "iam:PutRolePolicy", "iam:GetRolePolicy", "iam:DeleteRolePolicy",
      "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:PutRolePermissionsBoundary",
      "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole", "iam:ListRoleTags",
      "iam:CreateInstanceProfile", "iam:DeleteInstanceProfile", "iam:GetInstanceProfile",
      "iam:AddRoleToInstanceProfile", "iam:RemoveRoleFromInstanceProfile",
      "iam:TagInstanceProfile", "iam:UntagInstanceProfile", "iam:ListInstanceProfileTags",
      "iam:PassRole",
    ]
    resources = [
      "arn:${local.partition}:iam::${local.account_id}:role/agentic-*",
      "arn:${local.partition}:iam::${local.account_id}:instance-profile/agentic-*",
    ]
  }

  # Las claves AWS gestionadas (aws/ssm, aws/ebs) conceden acceso con Principal "*" y
  # kms:ViaService; ese tipo de concesión SÍ queda limitado por la boundary.
  statement {
    sid    = "KmsViaManagedServices"
    effect = "Allow"
    actions = [
      "kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey", "kms:CreateGrant",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.region}.amazonaws.com", "ec2.${var.region}.amazonaws.com"]
    }
  }

  statement {
    sid       = "ServiceLinkedRoles"
    effect    = "Allow"
    actions   = ["iam:CreateServiceLinkedRole"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "iam:AWSServiceName"
      values   = ["autoscaling.amazonaws.com", "elasticloadbalancing.amazonaws.com"]
    }
  }

  statement {
    sid       = "IamRead"
    effect    = "Allow"
    actions   = ["iam:GetPolicy", "iam:GetPolicyVersion", "iam:ListPolicyVersions"]
    resources = ["*"]
  }

  statement {
    sid       = "AssumeProjectRoles"
    effect    = "Allow"
    actions   = ["sts:AssumeRole", "sts:TagSession"]
    resources = ["arn:${local.partition}:iam::${local.account_id}:role/agentic-*"]
  }

  # --- Guardas: nada que permita escapar del techo ---------------------------
  statement {
    sid    = "DenyBoundaryTampering"
    effect = "Deny"
    actions = [
      "iam:DeleteRolePermissionsBoundary",
      "iam:CreatePolicyVersion", "iam:DeletePolicy", "iam:DeletePolicyVersion", "iam:SetDefaultPolicyVersion",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "DenyRolesWithoutBoundary"
    effect    = "Deny"
    actions   = ["iam:CreateRole", "iam:PutRolePermissionsBoundary"]
    resources = ["*"]
    condition {
      test     = "StringNotEquals"
      variable = "iam:PermissionsBoundary"
      values   = [local.boundary_arn]
    }
  }

  statement {
    sid    = "DenyIdentityEscalation"
    effect = "Deny"
    actions = [
      "iam:CreateUser", "iam:CreateAccessKey", "iam:CreateLoginProfile", "iam:AttachUserPolicy", "iam:PutUserPolicy",
      "iam:CreateOpenIDConnectProvider", "iam:UpdateOpenIDConnectProviderThumbprint", "iam:CreateSAMLProvider",
      "organizations:*", "account:*",
    ]
    resources = ["*"]
  }

  statement {
    sid     = "DenyTouchingPersistentRoles"
    effect  = "Deny"
    actions = ["iam:*"]
    # La boundary solo limita a los roles que la llevan: el usuario admin que aplica
    # este stack no se ve afectado.
    resources = [for r in local.persistent_roles : "arn:${local.partition}:iam::${local.account_id}:role/${r}"]
  }
}

resource "aws_iam_policy" "boundary" {
  name        = local.boundary_name
  description = "Permissions boundary obligatoria para todos los roles agentic-* (ADR-0002 §2)."
  policy      = data.aws_iam_policy_document.boundary.json
}

locals {
  persistent_roles = compact([
    "agentic-github-actions",
    var.github_reaper_environment != "" ? "agentic-github-reaper" : "",
    var.github_observability_environment != "" ? "agentic-github-observability" : "",
  ])
}

# -----------------------------------------------------------------------------
# Política de Terraform para envs/lab (la usa role/agentic-github-actions y, con
# denegaciones de creación, role/agentic-github-reaper).
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "terraform_lab" {
  statement {
    sid    = "LabInfrastructure"
    effect = "Allow"
    actions = [
      "ec2:*",
      "elasticloadbalancing:*",
      "autoscaling:*",
      "tag:GetResources",
      "cloudwatch:GetMetricData",
      "cloudwatch:ListMetrics",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.region]
    }
  }

  statement {
    sid    = "ClusterParameters"
    effect = "Allow"
    actions = [
      "ssm:PutParameter", "ssm:GetParameter", "ssm:GetParameters", "ssm:DeleteParameter",
      "ssm:AddTagsToResource", "ssm:RemoveTagsFromResource", "ssm:ListTagsForResource",
    ]
    resources = ["arn:${local.partition}:ssm:${var.region}:${local.account_id}:parameter/agentic-platform/cluster/*"]
  }

  statement {
    sid       = "PublicAmiParameters"
    effect    = "Allow"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = ["arn:${local.partition}:ssm:${var.region}::parameter/aws/service/*"]
  }

  statement {
    sid       = "DescribeParameters"
    effect    = "Allow"
    actions   = ["ssm:DescribeParameters"]
    resources = ["*"]
  }

  statement {
    sid     = "TerraformState"
    effect  = "Allow"
    actions = ["s3:ListBucket", "s3:GetBucketLocation", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      aws_s3_bucket.state.arn,
      "${aws_s3_bucket.state.arn}/lab/*",
    ]
  }

  statement {
    sid    = "ProjectRolesWithBoundary"
    effect = "Allow"
    actions = [
      "iam:CreateRole", "iam:PutRolePermissionsBoundary",
    ]
    resources = ["arn:${local.partition}:iam::${local.account_id}:role/agentic-*"]
    condition {
      test     = "StringEquals"
      variable = "iam:PermissionsBoundary"
      values   = [local.boundary_arn]
    }
  }

  statement {
    sid    = "ProjectRolesManage"
    effect = "Allow"
    actions = [
      "iam:DeleteRole", "iam:GetRole", "iam:TagRole", "iam:UntagRole", "iam:UpdateRole",
      "iam:UpdateRoleDescription", "iam:UpdateAssumeRolePolicy",
      "iam:PutRolePolicy", "iam:GetRolePolicy", "iam:DeleteRolePolicy",
      "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole", "iam:ListRoleTags",
      "iam:CreateInstanceProfile", "iam:DeleteInstanceProfile", "iam:GetInstanceProfile",
      "iam:AddRoleToInstanceProfile", "iam:RemoveRoleFromInstanceProfile",
      "iam:TagInstanceProfile", "iam:UntagInstanceProfile", "iam:ListInstanceProfileTags",
    ]
    resources = [
      "arn:${local.partition}:iam::${local.account_id}:role/agentic-*",
      "arn:${local.partition}:iam::${local.account_id}:instance-profile/agentic-*",
    ]
  }

  statement {
    sid       = "AttachOnlySsmCore"
    effect    = "Allow"
    actions   = ["iam:AttachRolePolicy", "iam:DetachRolePolicy"]
    resources = ["arn:${local.partition}:iam::${local.account_id}:role/agentic-*"]
    condition {
      test     = "ArnEquals"
      variable = "iam:PolicyARN"
      values   = ["arn:${local.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"]
    }
  }

  statement {
    sid       = "PassNodeRolesToEc2"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = ["arn:${local.partition}:iam::${local.account_id}:role/agentic-*"]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ec2.amazonaws.com"]
    }
  }

  statement {
    sid       = "ReadPolicies"
    effect    = "Allow"
    actions   = ["iam:GetPolicy", "iam:GetPolicyVersion", "iam:ListPolicyVersions", "sts:GetCallerIdentity"]
    resources = ["*"]
  }

  statement {
    sid       = "ServiceLinkedRoles"
    effect    = "Allow"
    actions   = ["iam:CreateServiceLinkedRole"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "iam:AWSServiceName"
      values   = ["autoscaling.amazonaws.com", "elasticloadbalancing.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "github_trust" {
  for_each = local.github_roles

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Igualdad exacta: ninguna rama, PR ni fork obtiene credenciales.
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values   = ["${var.github_oidc_subject_prefix}:environment:${each.value}"]
    }
  }
}

locals {
  github_roles = merge(
    { "agentic-github-actions" = var.github_lab_environment },
    var.github_reaper_environment != "" ? { "agentic-github-reaper" = var.github_reaper_environment } : {},
    var.github_observability_environment != "" ? { "agentic-github-observability" = var.github_observability_environment } : {},
  )
}

resource "aws_iam_role" "github" {
  for_each = local.github_roles

  name                 = each.key
  description          = "GitHub Actions (${var.github_repository}, environment ${each.value}) vía OIDC."
  assume_role_policy   = data.aws_iam_policy_document.github_trust[each.key].json
  max_session_duration = 3600
  permissions_boundary = aws_iam_policy.boundary.arn
}

resource "aws_iam_role_policy" "github_actions" {
  name   = "terraform-lab"
  role   = aws_iam_role.github["agentic-github-actions"].id
  policy = data.aws_iam_policy_document.terraform_lab.json
}

# El reaper solo destruye: misma política que Terraform, pero sin poder crear nada.
data "aws_iam_policy_document" "reaper_deny_create" {
  source_policy_documents = [data.aws_iam_policy_document.terraform_lab.json]

  statement {
    sid    = "ReaperCannotCreate"
    effect = "Deny"
    actions = [
      "ec2:RunInstances", "ec2:CreateVpc", "ec2:CreateSubnet", "ec2:CreateSecurityGroup", "ec2:CreateLaunchTemplate",
      "ec2:CreateLaunchTemplateVersion", "ec2:CreateInternetGateway", "ec2:CreateRouteTable", "ec2:CreateRoute",
      "ec2:AuthorizeSecurityGroupIngress", "ec2:AuthorizeSecurityGroupEgress", "ec2:AllocateAddress",
      "elasticloadbalancing:CreateLoadBalancer", "elasticloadbalancing:CreateTargetGroup", "elasticloadbalancing:CreateListener",
      # UpdateAutoScalingGroup no se deniega: terraform destroy vacía el ASG (min/max/desired = 0) antes de borrarlo.
      "autoscaling:CreateAutoScalingGroup", "autoscaling:SetDesiredCapacity",
      "iam:CreateRole", "iam:PutRolePolicy", "iam:AttachRolePolicy", "iam:CreateInstanceProfile", "iam:UpdateAssumeRolePolicy",
      "iam:PassRole",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_reaper" {
  count  = var.github_reaper_environment != "" ? 1 : 0
  name   = "terraform-lab-destroy-only"
  role   = aws_iam_role.github["agentic-github-reaper"].id
  policy = data.aws_iam_policy_document.reaper_deny_create.json
}

data "aws_iam_policy_document" "observability_state" {
  statement {
    sid       = "ObservabilityState"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.state.arn}/observability/*"]
  }
  statement {
    sid       = "ListStateBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.state.arn]
  }
}

resource "aws_iam_role_policy" "github_observability" {
  count  = var.github_observability_environment != "" ? 1 : 0
  name   = "observability-state"
  role   = aws_iam_role.github["agentic-github-observability"].id
  policy = data.aws_iam_policy_document.observability_state.json
}
