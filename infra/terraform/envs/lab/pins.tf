# Versiones fijadas de L1 (docs/versions.md). K3s, AWS CCM y Cluster Autoscaler
# comparten la minor 1.35. Los sha256 se verifican en el user-data.
locals {
  pins = {
    # https://github.com/k3s-io/k3s/releases/tag/v1.35.10%2Bk3s1 (sha256sum-amd64.txt)
    k3s_version   = "v1.35.10+k3s1"
    k3s_sha256    = "5cd49f0faca5b2ea4355d4761e7b1445b8aa05cd50e612fd9c370551db49e5e2"
    airgap_sha256 = "c10a9f07c357cfc41488f29c15872621ac8664c9864b3d1148a10155c9a1c2ff"
    # install.sh de la misma etiqueta (raw.githubusercontent.com/k3s-io/k3s/<tag>/install.sh).
    install_sh_sha256 = "8598e002e61d658fed7b7542fc6d2c66d8da6eae69e088830105d2ee1ffb6d91"
    # AWS CLI v2: AWS solo publica firma PGP; sha256 calculado sobre el zip oficial el 2026-11-07.
    awscli_version = "2.39.6"
    awscli_sha256  = "7a121264f2637a3b90767aaf5bdd43ee88b8c925a931d0479fa2ce22b1a2fa76"
  }
}
