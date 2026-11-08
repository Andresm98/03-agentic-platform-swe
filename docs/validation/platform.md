# Validación de la capa de plataforma (equipo P)

Validaciones **locales y estáticas** de 2026-11-07/08. **Nada de esto se ha desplegado:** no hubo `terraform plan` ni `apply` contra AWS, ni recursos en AWS, GitHub o Grafana, ni commit ni push. Que un chart renderice o Terraform valide no demuestra que funcione en el cluster.

## 1. Validaciones ejecutadas

| Comando | Resultado real |
|---|---|
| `VALIDATE_HELM=1 bash infra/scripts/validate.sh` | **rc=0.** `terraform fmt` OK; `terraform validate` OK en cada raíz y módulo; `bash -n` OK; YAML OK; `kustomize build` OK; `helm template` OK en los 8 Applications con chart. tflint, checkov, shellcheck y kubeconform: **omitidos, no instalados** |
| `helm template` de cada chart con sus values finales, incluidos los de bootstrap | OK: argo-cd 10.15.0 (52 objetos), aws-cloud-controller-manager 0.0.12 (7), traefik 42.3.1 (8), nats 2.15.2 (5), external-secrets 2.14.0 + overlay aws-lab (44), cluster-autoscaler 9.59.0 (8), keda 2.21.0 (29), dapr 1.19.1 (42), dapr-dashboard 0.15.0 (5), k8s-monitoring 4.6.0 (35). Overlay local: traefik (8), nats (5) |
| Registries de las líneas `image:` renderizadas | ghcr.io 23, quay.io 8, registry.k8s.io 3, ecr-public.aws.com 1; **ninguna de docker.io**. Alloy se fija en el mirror dentro del CR `Alloy` |
| `kubectl kustomize --load-restrictor LoadRestrictionsNone gitops/clusters/local-k3d` | OK, 8 Applications |
| Render de los user-data con `templatefile` y ARN ficticios (config sin providers en el scratchpad, sin contacto con AWS, mediante `terraform apply` local) | OK. `bash -n` OK en ambos. Tras gzip+base64: server 6984 bytes, agent 3572 (límite 16384) |
| `DRY_RUN=1 ... seed-secrets.sh` con variables ficticias | 12 parámetros, ninguno vacío, incluido `langsmith-api-key`. Sin `LANGSMITH_API_KEY` u otras obligatorias: rc=1 con la lista de las que faltan |
| Auditoría de `.github/workflows/*.yml` con Python | Todas las `uses:` fijadas por SHA de 40 caracteres; `permissions` mínimos en la raíz; sin `pull_request_target`, `secrets: inherit`, `kubectl apply` ni `helm install` |
| JSON de los 6 dashboards | Parsean; IDs de panel únicos |

### Resueltos de fuentes reales (2026-11-07/08)

K3s `v1.35.10+k3s1` con sha256 de `sha256sum-amd64.txt`; `install.sh` de la misma etiqueta y zip de AWS CLI 2.39.6 con sha256 calculado sobre la descarga; tags de `registry.k8s.io` (CCM y CA `v1.35.3`); `ghcr.io/dapr/dashboard:0.15.0`; digests de Docker Hub en `platform-images.lock`; SHAs de acciones con `git ls-remote`; checksum de kubeconform de su fichero `CHECKSUMS`.

### Errores reales que encontró la validación y ya están corregidos

- `seed-secrets.sh` escribía valores **vacíos** con el alias `python3` de la Microsoft Store: ahora detecta un Python operativo, asigna antes de usar y rechaza valores vacíos.
- Nombres de métricas de NATS: el chart usa `-prefix=nats`, así que son `nats_stream_*`, `nats_consumer_*` y `nats_varz_*` (comprobado en el código del exporter v0.20.2), no `jetstream_*` ni `gnatsd_*`.
- `app` en `annotationAutodiscovery` y la clave del nombre de log de Traefik (`log`, no `logs`).
- Se pasó de argo-cd 10.14.0 y traefik 42.3.0 a 10.15.0 y 42.3.1 tras la decisión del coordinador.

## 2. Sin verificar

**No se ejecutaron localmente:** shellcheck, kubeconform, tflint y checkov. La descarga de los binarios de shellcheck y kubeconform fue bloqueada por una política de la sesión. Corren por primera vez en `_iac-scan.yml` con `STRICT=1` y pueden dar hallazgos. Los workflows no se han ejecutado nunca.

**Comportamiento en cluster, sin evidencia:** todo lo de la Verificación de los ADR: join de K3s, CCM, CA, NLB, GitOps, ESO, Notifications.

**`TODO(verify)` en el código:**

| Dónde | Qué |
|---|---|
| `envs/lab/terraform.tfvars.example` | AMI de Ubuntu 24.04 (requiere consultar SSM de AWS) |
| `envs/lab/terraform.tfvars.example` | Cuenta AWS de Grafana Cloud para el datasource |
| `observability/terraform/main.tf` | `authType = grafana_assume_role` en el stack de Grafana Cloud |
| `gitops/platform/redis/statefulset.yaml` | Redis 8.x como actor state store (se usa 7.4.12) |

## 3. Desviaciones respecto al contrato o los ADR

| Desviación | Motivo |
|---|---|
| Imagen del CCM `v1.35.3` (el coordinador indicó `v1.35.2`) | `v1.35.3` existe en `registry.k8s.io`; misma minor |
| `lab-reaper.yml` usa el environment **`lab-reaper`** sin revisores y `role/agentic-github-reaper` (solo destruye), en vez de `lab` | Con revisores en `lab`, cada cron espera aprobación y el reaper no protege. El trust de `agentic-github-actions` sigue siendo solo `environment:lab` |
| Rol añadido `role/agentic-github-observability` (solo estado `observability/*`) | `observability.yml` necesita estado remoto y usa su environment |
| `lab.yml` pide **dos aprobaciones** (plan y apply) | ADR-0001 exige plan visible antes de aplicar; ambos jobs necesitan OIDC |
| Plan binario en el bucket privado, no como artifact | El repo es público y el plan contiene el join token tras el refresh |
| El join token **sí llega al estado** de Terraform | Plan §1.1 #7 dice que no, pero `ignore_changes = [value]` solo evita el diff; el refresh lo guarda. Mitigado: bucket privado y cifrado. Alternativa: `value_wo` |
| Flags de K3s añadidos a ADR-0002 §1: `--node-ip` y `--secrets-encryption` | Dirección de nodo explícita y Secrets cifrados en el datastore |
| Dapr Scheduler con **3 réplicas** en el CP | `replicas: 3` fijo en el chart 1.19.1, aun sin HA |
| Alloy logs y node-exporter también en el CP | Para tener logs y métricas del CP; no cambia la capacidad de los workers |
| Línea 1.35 y charts más nuevos que el plan (k8s-monitoring 4.x, nats 2.x, ESO 2.x) | Decisión del coordinador; values escritos contra esos esquemas |
| Ficheros auxiliares: `templates/common.sh.tftpl`, `infra/scripts/{lib,demo-aws}.sh`, `envs/lab/pins.tf` | Evitar lógica duplicada |
| No implementada la alerta de Grafana por `llm_tokens_total{mode="live"}` (ADR-0002 §6) | Fuera del alcance del bloque D; pendiente |

**Contrato nuevo para el equipo A:** una Application crea GitHub Deployments si lleva la label `agentic.io/github-deployment: "true"` y tiene **una sola fuente Git** (`spec.source`).

## 4. Riesgos antes del primer `lab.yml up`

1. **Ejecutar `mirror-images.yml` y hacer públicos los paquetes** antes de levantar: sin ello, Traefik, NATS, Redis y Alloy fallan con ImagePull.
2. Configurar en GitHub los environments `lab`, `lab-reaper` y `observability` y sus variables (ver cabecera de cada workflow); aplicar `make bootstrap` y `make seed-secrets`.
3. Taint `NoExecute` en el CP, sin probar: que los jobs del helm-controller (Argo CD) y los pods auxiliares de `local-path` lo toleren. Si no, Argo CD no se instala o los PVC de NATS, Redis y Dapr se quedan Pending.
4. `AWS_CONFIG_FILE` con `credential_source=Ec2InstanceMetadata` en CCM, CA y ESO: sin probar en cada SDK.
5. Permisos NATS por subject frente a Dapr: si los consumidores usan subjects de entrega fuera de `_INBOX.>`, habrá rechazos. `$JS.API.>` es amplio para los agentes.
6. `agentic-boundary` incluye `kms` vía SSM/EC2 porque las claves AWS gestionadas conceden con `Principal: *`: sin probar, y es el primer punto a revisar si falla un `SecureString` o un volumen cifrado.
7. La lista de permisos de `agentic-github-actions` puede quedarse corta: se verá en el primer apply.
8. Un rol creado por `agentic-github-actions` lleva la boundary, que permite leer SSM; su trust no se puede restringir. Lo mitiga la aprobación del environment.
9. Los paneles usan métricas de la §5 del plan y de exporters sin comprobar contra datos reales (p. ej. `nats_varz_jetstream_stats_storage`).
10. Perfil local: sin `k8s-monitoring` no existe `alloy-otlp`, y las Applications hijas leen `main` aunque se use `GITOPS_REVISION`.

## Corrección posterior: join token fuera del estado

`aws_ssm_parameter.join_token` pasó de `value` + `ignore_changes` a `value_wo` + `value_wo_version`. Comprobado en el código del provider v6.72.0 (`internal/service/ssm/parameter.go`): con `has_value_wo` activo, el read ejecuta `d.Set(value, nil)`. `required_version` sube a `>= 1.11.0` en el módulo `control-plane` y en `envs/lab`. Sin probar contra AWS.
