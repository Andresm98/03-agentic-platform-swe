# Responsabilidad: escritorio Windows dentro de la VPC para abrir Argo CD y Dapr Dashboard desde el
# navegador, con Fleet Manager Remote Desktop. No tiene puertos de entrada: las interfaces no salen
# a Internet. La contraseña la genera la propia VM y solo existe en SSM, nunca en el estado.

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

data "aws_ssm_parameter" "windows_ami" {
  name = "/aws/service/ami-windows-latest/Windows_Server-2022-English-Full-Base"
}

# Por nombre, no por referencia al módulo: así -target no arrastra el ASG ni el NLB.
data "aws_lb" "public" {
  name = "${var.cluster_name}-nlb"
}

locals {
  name      = "${var.cluster_name}-ui-desktop"
  partition = data.aws_partition.current.partition
  region    = data.aws_region.current.region
  tags      = merge(var.tags, { Name = local.name, "platform.io/role" = "ui-desktop" })

  password_arn = "arn:${local.partition}:ssm:${local.region}:${data.aws_caller_identity.current.account_id}:parameter${var.password_parameter_name}"
}

# --- Red ---------------------------------------------------------------------------
resource "aws_security_group" "this" {
  name        = local.name
  description = "Escritorio de interfaces: sin entrada; salida a SSM, interfaces y ejercicios"
  vpc_id      = var.vpc_id
  tags        = local.tags
}

resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.this.id
  description       = "Agente SSM y Fleet Manager"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "http" {
  security_group_id = aws_security_group.this.id
  description       = "Ejercicios de estudiantes por el NLB"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "interfaces" {
  security_group_id            = aws_security_group.this.id
  description                  = "NodePort de Argo CD y Dapr Dashboard"
  ip_protocol                  = "tcp"
  from_port                    = var.nodeport_from
  to_port                      = var.nodeport_to
  referenced_security_group_id = var.control_plane_security_group_id
}

resource "aws_vpc_security_group_ingress_rule" "control_plane_interfaces" {
  security_group_id            = var.control_plane_security_group_id
  description                  = "Interfaces desde el escritorio"
  ip_protocol                  = "tcp"
  from_port                    = var.nodeport_from
  to_port                      = var.nodeport_to
  referenced_security_group_id = aws_security_group.this.id
}

# --- Identidad ---------------------------------------------------------------------
data "aws_iam_policy_document" "trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name                 = "agentic-ui-desktop"
  description          = "Escritorio de interfaces: SSM y su propia contraseña"
  assume_role_policy   = data.aws_iam_policy_document.trust.json
  permissions_boundary = var.permissions_boundary_arn
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "password" {
  statement {
    sid       = "PublishPassword"
    effect    = "Allow"
    actions   = ["ssm:PutParameter"]
    resources = [local.password_arn]
  }
}

resource "aws_iam_role_policy" "password" {
  name   = "publish-password"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.password.json
}

resource "aws_iam_instance_profile" "this" {
  name = "agentic-ui-desktop"
  role = aws_iam_role.this.name
}

# --- Contraseña --------------------------------------------------------------------
# Mismo patrón que el join token: value_wo deja fuera del estado el valor real que escribe la VM.
resource "aws_ssm_parameter" "password" {
  name             = var.password_parameter_name
  description      = "Contraseña de Administrator del escritorio (la escribe la VM)."
  type             = "SecureString"
  value_wo         = "pending-bootstrap"
  value_wo_version = 1
}

# --- Instancia ---------------------------------------------------------------------
resource "aws_instance" "this" {
  ami                    = data.aws_ssm_parameter.windows_ami.value
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [aws_security_group.this.id]
  iam_instance_profile   = aws_iam_instance_profile.this.name
  monitoring             = false

  # El user-data solo corre en el primer arranque: si cambia, la VM debe recrearse.
  user_data_replace_on_change = true

  user_data = <<-EOT
    <powershell>
    $ErrorActionPreference = 'Stop'
    $bytes = New-Object byte[] 18
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $password = 'Aa1!' + ([Convert]::ToBase64String($bytes) -replace '[+/=]', 'x')
    Set-LocalUser -Name Administrator -Password (ConvertTo-SecureString $password -AsPlainText -Force)
    Write-SSMParameter -Region ${local.region} -Name '${var.password_parameter_name}' -Type SecureString -Value $password -Overwrite $true | Out-Null
    Set-Content -Path 'C:\Users\Public\Desktop\Argo CD.url' -Value "[InternetShortcut]`r`nURL=http://${var.control_plane_ip}:${var.argocd_nodeport}/"
    Set-Content -Path 'C:\Users\Public\Desktop\Dapr Dashboard.url' -Value "[InternetShortcut]`r`nURL=http://${var.control_plane_ip}:${var.dapr_nodeport}/"
    New-Item -ItemType Directory -Force -Path 'C:\ui-desktop' | Out-Null
    @'
    $page = 'C:\Users\Public\Desktop\Ejercicios.html'
    $base = 'http://${data.aws_lb.public.dns_name}/s'
    try {
      $url = 'https://api.github.com/repos/${var.github_repository}/contents/gitops/stage?ref=stage'
      $names = (Invoke-RestMethod -UseBasicParsing -Uri $url) | Where-Object { $_.type -eq 'dir' } | ForEach-Object { $_.name }
      $items = $names | ForEach-Object { "<li><a href='$base/$_/'>$_</a></li>" }
      if (-not $items) { $items = '<li>No hay ejercicios publicados.</li>' }
    } catch {
      $items = '<li>No se pudo leer la lista. Usa Actualizar ejercicios.</li>'
    }
    Set-Content -Encoding UTF8 -Path $page -Value "<!doctype html><meta charset='utf-8'><title>Ejercicios</title><h1>Ejercicios de estudiantes</h1><ul>$items</ul>"
    '@ | Set-Content -Path 'C:\ui-desktop\ejercicios.ps1'
    Set-Content -Path 'C:\Users\Public\Desktop\Actualizar ejercicios.cmd' -Value 'powershell -ExecutionPolicy Bypass -File C:\ui-desktop\ejercicios.ps1'
    & powershell -ExecutionPolicy Bypass -File 'C:\ui-desktop\ejercicios.ps1'
    </powershell>
  EOT

  credit_specification {
    cpu_credits = "unlimited"
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size_gb
    encrypted             = true
    delete_on_termination = true
    tags                  = local.tags
  }

  tags = local.tags

  # El parámetro público cambia con cada AMI nueva; no debe recrear la VM.
  lifecycle {
    ignore_changes = [ami]
  }

  depends_on = [aws_ssm_parameter.password, aws_iam_role_policy.password, aws_iam_role_policy_attachment.ssm_core]
}
