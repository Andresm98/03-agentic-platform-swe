# L0: infraestructura AWS del lab (ADR-0001 §1). La ejecuta lab.yml (OIDC) o, como respaldo, make up.

resource "time_static" "created_at" {}

locals {
  common_tags = {
    Project   = "agentic-platform"
    Lifecycle = "ephemeral"
    Owner     = var.owner
    ManagedBy = "terraform/envs/lab"
  }

  control_plane_ip       = "10.0.1.10"
  join_token_parameter   = "/agentic-platform/cluster/join-token"
  join_token_placeholder = "pending-bootstrap"
}

data "aws_availability_zones" "available" {
  state = "available"
}

module "network" {
  source = "../../modules/network"

  cluster_name = var.cluster_name
  vpc_cidr     = "10.0.0.0/16"
  public_subnets = [
    { az = data.aws_availability_zones.available.names[0], cidr = "10.0.1.0/24" },
    { az = data.aws_availability_zones.available.names[1], cidr = "10.0.2.0/24" },
  ]
  allowed_cidrs = var.allowed_cidrs
  created_at    = time_static.created_at.rfc3339
}

module "iam" {
  source = "../../modules/iam"

  cluster_name              = var.cluster_name
  permissions_boundary_arn  = var.permissions_boundary_arn
  join_token_parameter_name = local.join_token_parameter
}

module "control_plane" {
  source = "../../modules/control-plane"

  cluster_name              = var.cluster_name
  ami_id                    = var.ami_id
  instance_type             = var.control_plane_instance_type
  subnet_id                 = module.network.control_plane_subnet_id
  private_ip                = local.control_plane_ip
  security_group_ids        = [module.network.control_plane_security_group_id]
  instance_profile_name     = module.iam.cp_instance_profile_name
  user_data                 = local.server_user_data
  join_token_parameter_name = local.join_token_parameter
  join_token_placeholder    = local.join_token_placeholder
  tags                      = local.common_tags
}

module "workers" {
  source = "../../modules/workers"

  cluster_name          = var.cluster_name
  ami_id                = var.ami_id
  instance_type         = var.worker_instance_type
  subnet_ids            = module.network.public_subnet_ids
  security_group_ids    = [module.network.workers_security_group_id]
  instance_profile_name = module.iam.worker_instance_profile_name
  user_data             = local.agent_user_data
  capacity              = { min = 1, desired = 1, max = 2 }
  tags                  = local.common_tags

  # Los workers esperan el token con backoff; lanzarlos antes que el CP solo gasta tiempo.
  depends_on = [module.control_plane]
}

module "nlb" {
  source = "../../modules/nlb"

  cluster_name       = var.cluster_name
  vpc_id             = module.network.vpc_id
  subnet_ids         = module.network.public_subnet_ids
  security_group_ids = [module.network.nlb_security_group_id]
  asg_name           = module.workers.asg_name
}

module "observability_aws" {
  source = "../../modules/observability-aws"
  count  = var.grafana_cloud_aws_account_id != "" && var.grafana_cloudwatch_external_id != "" ? 1 : 0

  permissions_boundary_arn     = var.permissions_boundary_arn
  grafana_cloud_aws_account_id = var.grafana_cloud_aws_account_id
  external_id                  = var.grafana_cloudwatch_external_id
}
