# Renderizado de L1: user-data del server y del agent, más los manifests de
# kubernetes/bootstrap/ inyectados vía templatefile (ADR-0001 §1). Los cambios solo
# afectan a labs nuevos: el CP ignora cambios de user_data.

locals {
  repo_root     = "${path.module}/../../../.."
  templates_dir = "${path.module}/../../templates"
  bootstrap_dir = "${local.repo_root}/kubernetes/bootstrap"
  controller    = module.iam.controller_role_arns

  common_functions = templatefile("${local.templates_dir}/common.sh.tftpl", merge(local.pins, {
    region = var.region
  }))

  bootstrap_manifests = {
    "agentic-aws-controller-config.yaml" = templatefile("${local.bootstrap_dir}/aws-controller-config.yaml.tftpl", {
      ccm_role_arn                = local.controller["ccm"]
      cluster_autoscaler_role_arn = local.controller["cluster_autoscaler"]
      external_secrets_role_arn   = local.controller["external_secrets"]
      region                      = var.region
    })
    "agentic-aws-ccm.yaml" = templatefile("${local.bootstrap_dir}/aws-ccm.yaml.tftpl", {
      region = var.region
    })
    "agentic-argocd.yaml" = file("${local.bootstrap_dir}/argocd.yaml")
  }

  server_user_data = templatefile("${local.templates_dir}/server-userdata.sh.tftpl", {
    common_functions     = local.common_functions
    join_token_parameter = local.join_token_parameter
    bootstrap_manifests  = local.bootstrap_manifests
    root_app_manifest    = file("${local.repo_root}/gitops/root-app.yaml")
  })

  agent_user_data = templatefile("${local.templates_dir}/agent-userdata.sh.tftpl", {
    common_functions       = local.common_functions
    join_token_parameter   = local.join_token_parameter
    join_token_placeholder = local.join_token_placeholder
    control_plane_ip       = local.control_plane_ip
  })
}

check "user_data_size" {
  assert {
    condition     = length(base64gzip(local.server_user_data)) < 16384 && length(base64gzip(local.agent_user_data)) < 16384
    error_message = "El user-data comprimido supera el límite de 16 KB de EC2."
  }
}
