# Runbook: troubleshooting por fase

Problemas conocidos y cómo diagnosticarlos. Las causas vienen del [plan §1.1 y §1.2](IMPLEMENTATION_PLAN.md#1-ajustes-críticos-al-brief) y de los ADRs. Cada problema nuevo que aparezca en un ensayo se añade aquí con su síntoma, diagnóstico y solución, y la evidencia va a [`validation-log.md`](validation-log.md).

> Acceso al cluster: siempre por el túnel SSM (`make tunnel`). No hay SSH ni 6443 público. Para una shell en un nodo: `aws ssm start-session --target <instance-id>`.

## Comandos de diagnóstico rápidos

```bash
kubectl get nodes -o wide -L platform.io/pool
kubectl get nodes -o custom-columns=NAME:.metadata.name,PROVIDER:.spec.providerID,TAINTS:.spec.taints[*].key
kubectl get events -A --sort-by=.lastTimestamp | tail -40
kubectl -n argocd get applications
kubectl -n kube-system logs deploy/cluster-autoscaler-aws-cluster-autoscaler --tail=100
kubectl -n kube-system get cm cluster-autoscaler-status -o yaml
# En un nodo (vía SSM):
sudo journalctl -u k3s -u k3s-agent --no-pager | tail -100
sudo cat /var/log/cloud-init-output.log | tail -100
```

## Fase 0: prerrequisitos y trabajo local

| Síntoma | Causa probable | Solución |
|---|---|---|
| `bash\r: No such file or directory` o `$'\r': command not found` al ejecutar un `.sh` | Finales de línea CRLF (Windows) | `.gitattributes` fuerza LF en `*.sh`. Si el archivo ya estaba en el índice: `git add --renormalize .` |
| `docker: Cannot connect to the Docker daemon` | Docker Desktop parado | Arrancar Docker Desktop y esperar a que `docker info` responda |
| `SessionManagerPlugin is not found` | Falta `session-manager-plugin` | Instalarlo (plan §0); sin él no hay túnel |
| `make: command not found` en Windows | Git Bash no incluye GNU make | Instalar `make` (p. ej. `winget`/`choco`) o ejecutar el script del target directamente con `bash` |
| pre-commit `gitleaks` bloquea un commit | Un secreto real (o un falso positivo) en el diff | Si es real: sacarlo, rotarlo y moverlo a SSM. Si es ficticio: usar un archivo `*.example` o un valor que contenga `example`/`dummy` |
| La tarea e2e en compose consume tokens `live` | `LLM_GLOBAL_MODE` distinto de `simulated` | En desarrollo siempre `simulated`; comprobar `llm_tokens_total{mode="live"}` = 0 |
| k3d: `ImagePullBackOff` en imágenes de plataforma | Límite de pulls de Docker Hub o tag sin mirror | Usar las imágenes del mirror en GHCR (`platform-images.lock`) |

## Fase A: Terraform e infraestructura AWS

| Síntoma | Causa probable | Solución |
|---|---|---|
| `Error acquiring the state lock` | Ejecución previa interrumpida (lock en S3, `use_lockfile`) | Confirmar que no hay otro `apply` en curso (`lab.yml`, concurrency `lab`) y `terraform force-unlock <id>` |
| `terraform plan` quiere cambiar `desired_capacity` | Falta `ignore_changes = [desired_capacity]` en el ASG | Añadirlo; el dueño en ejecución es el CA (ADR-0001 §1) |
| `plan` quiere recrear el control plane | Cambió la AMI o el user-data | Fijar la AMI en una variable e `ignore_changes = [ami, user_data]`. Recrear el CP **pierde el datastore** (single control plane, sin HA) |
| Instancias no aparecen `Online` en SSM Fleet Manager | Sin egress 443, o falta la política SSM core en el rol | Revisar SG de egress y el instance profile |
| `lab.yml` no puede asumir el rol (OIDC) | El `sub` no coincide con el que emite GitHub. El repositorio usa el formato inmutable: `repo:Andresm98@41342993/03-agentic-platform-swe@1449959239:environment:lab` | Comparar `gh api repos/Andresm98/03-agentic-platform-swe/actions/oidc/customization/sub` con la trust policy, y comprobar que el job use `environment: lab` |
| `iam:CreateRole` denegado a Terraform | Falta la permissions boundary o el prefijo `agentic-*` | Crear el rol con la boundary y el prefijo (ADR-0002 §2) |
| Más de 3 EC2 o instance refresh inesperado | Instance refresh o `AZRebalance` activos | `AZRebalance` suspendido y sin instance refresh (plan §1.1 #9) |

## Fase B: K3s

| Síntoma | Causa probable | Solución |
|---|---|---|
| Worker no se une; el log de cloud-init espera el token indefinidamente | El CP no publicó el join token en SSM, o el worker no tiene `ssm:GetParameter` | Revisar en el CP `aws ssm get-parameter --name /agentic-platform/cluster/join-token` y el rol del worker |
| `aws: command not found` en el user-data | Ubuntu 24.04 no trae AWS CLI | El user-data instala AWS CLI v2 con versión fijada antes de leer SSM |
| `Node password rejected` al unir un worker | Un worker nuevo reutiliza la IP (y el nombre) de uno eliminado cuyo `Node` sigue existiendo | `kubectl delete node <nombre>`; `cloud-node-lifecycle` del CCM debería hacerlo solo. El script `11-scale-down.sh` lo comprueba |
| Nodo con nombre distinto de `ip-…ec2.internal` | No se pasó `--node-name` con el `local-hostname` de IMDS | Corregir el user-data; el CCM busca la instancia por nombre de nodo |
| `spec.providerID` vacío o sin `aws:///` | Falta `--kubelet-arg=provider-id=aws:///<az>/<instance-id>` | Corregir el user-data. El CA empareja nodos con el ASG por `providerID` |
| IMDS devuelve 401 o el user-data no obtiene metadatos | IMDSv2 obligatorio y la petición no usa token | Usar `PUT /latest/api/token` antes de cada lectura |
| Pods del sistema en `ImagePullBackOff` (coredns, metrics-server) | El tarball airgap no está en `/var/lib/rancher/k3s/agent/images/` o no coincide con la versión | Descargar `k3s-airgap-images-amd64.tar.zst` de la misma versión y verificar `sha256sum-amd64.txt` |

## Fase C: AWS CCM, Argo CD y Cluster Autoscaler

| Síntoma | Causa probable | Solución |
|---|---|---|
| Todos los pods `Pending`; los nodos tienen el taint `node.cloudprovider.kubernetes.io/uninitialized` | El CCM no arrancó (con `cloud-provider=external` nada se programa hasta que el CCM inicializa el nodo) | Revisar el `HelmChart` del CCM (`spec.bootstrap: true`) en `/var/lib/rancher/k3s/server/manifests/` y sus logs. Debe tolerar el taint `uninitialized` y `CriticalAddonsOnly` |
| CCM: `failed to get instance` / `instance not found` | Nombre de nodo distinto del private DNS, o falta el tag `kubernetes.io/cluster/agentic-platform=owned` | Corregir el nombre (Fase B) y los tags de instancias, subnets y SGs |
| CCM intenta crear rutas o LBs | Controladores de más | `--controllers=cloud-node,cloud-node-lifecycle --configure-cloud-routes=false` |
| CCM o CA: `NoCredentialProviders` / `EC2RoleRequestError` | Hop limit de IMDS = 1 en el CP (los pods no llegan a IMDS) o el pod no está en el CP | `http_put_response_hop_limit = 2` **solo** en el CP; `nodeSelector` del control plane y toleración del taint |
| CA: `AccessDenied` en `SetDesiredCapacity` | El rol no se asume (falta `AWS_CONFIG_FILE` con `role_arn` + `credential_source = Ec2InstanceMetadata`) o el ASG no tiene el tag de la condición | Revisar el ConfigMap montado y los tags `k8s.io/cluster-autoscaler/*` del ASG |
| CA no descubre el ASG | Tags de auto-discovery incorrectos | `k8s.io/cluster-autoscaler/enabled=true` y `k8s.io/cluster-autoscaler/agentic-platform=owned` |
| CA: `node group min/max` correcto pero nunca escala | Minors distintas de K3s/CA/CCM o pods sin `requests` | Ver [versions.md](versions.md); los pods de prueba deben pedir CPU |
| Applications de Argo CD en `Unknown` / `ComparisonError` | Repo inaccesible o ruta mal escrita en `root-app.yaml` | Repo público, `repoURL` = `https://github.com/Andresm98/03-agentic-platform-swe` |

## Fase D: NLB y Traefik

| Síntoma | Causa probable | Solución |
|---|---|---|
| Targets `unhealthy` en el TG | Traefik no está en ese worker, el SG de workers no admite 30080 desde el SG del NLB, o `/ping` no está en el entrypoint `web` | `kubectl -n traefik get ds,pods -o wide`; revisar SG y `ping.entryPoint=web` |
| Un worker nuevo nunca pasa a healthy | El DaemonSet de Traefik no tolera o no selecciona el nodo | Selector `platform.io/pool=apps`; con `externalTrafficPolicy: Local` el nodo solo está healthy si su Traefik está listo (esperado) |
| `curl` al NLB da timeout desde fuera | SG del NLB sin `TCP 80` desde `allowed_cidrs` | Revisar `var.allowed_cidrs` |
| Ráfaga no devuelve `429` | El middleware no está referenciado | Annotation `traefik.ingress.kubernetes.io/router.middlewares: traefik-rate-limit@kubernetescrd,traefik-body-limit@kubernetescrd` |
| Scale-down lento en el NLB | Deregistration delay alto | 30 s (plan §1.2 #17) |

## Fase E: agentes y NATS en el cluster

| Síntoma | Causa probable | Solución |
|---|---|---|
| `ImagePullBackOff` en imágenes de GHCR | El paquete sigue **privado** (GHCR los crea privados) | Cambiarlo a *Public* en *Package settings*; comprobar con `docker pull` anónimo |
| `ImagePullBackOff` con `toomanyrequests` | Una imagen apunta a `docker.io` (límite de pulls anónimos) | Pasarla por `mirror-images.yml` y usar `ghcr.io/andresm98/agentic-platform/mirror/...@sha256:` |
| `readyz` no listo en los agentes | Sin conexión a NATS o el stream `TASKS` no existe | `nats stream info TASKS`; el Job de sync-wave 8 crea stream y consumidores |
| Cada réplica procesa el mismo mensaje | Suscripción core en lugar de consumidor durable pull | Consumidores durables de JetStream (uno por agente) |
| KEDA no escala desde cero | El consumidor durable no existe antes que las réplicas | Job de JetStream en sync-wave anterior a los agentes (CONTRACTS §7–8) |
| Pods del agente de ejecución reiniciados bajo carga | Trabajo de CPU en el event loop (probes fallan) | `ProcessPoolExecutor(max_workers=1)` (plan §1.1 #11) |
| Desde un pod de `apps` se alcanza `169.254.169.254` | Hop limit 2 en workers o NetworkPolicy de egress ausente | Hop limit 1 en workers + default-deny de egress |
| Sidecar `daprd` no arranca | Certificados de Sentry, componente mal definido o `scopes` | `kubectl logs <pod> -c daprd`; revisar `gitops/apps/dapr/` |
| Workflows no persisten | Redis no es `actorStateStore` o la contraseña no llegó por ESO | Componente `workflowstore` con `actorStateStore: "true"` y Secret `redis-auth` |

## Fase F: GitHub Actions + GHCR

| Síntoma | Causa probable | Solución |
|---|---|---|
| `denied: permission_denied` al hacer push a GHCR | Falta `packages: write` en el job | Permisos mínimos por job |
| El commit de promoción no dispara Argo | Argo aún no refresca (poll de 3 min) | Esperar o refrescar la Application; el commit con `GITHUB_TOKEN` no redispara workflows (intencionado) |
| Workflow falla al resolver una acción | Acción fijada por un SHA que no existe | Revisar el SHA y el comentario del tag; Dependabot los mantiene |

## Fase G: endurecimiento de Helm y Argo CD

| Síntoma | Causa probable | Solución |
|---|---|---|
| Un `kubectl edit` se revierte solo | `selfHeal: true` (esperado) | Los cambios se hacen siempre por Git |
| Borrar un archivo en Git borró un recurso | `prune: true` (esperado) | Los PVC de NATS y Redis llevan `Prune=false` |
| Application en `OutOfSync` permanente | Campos mutados por controladores (réplicas del HPA) | Los manifiestos no fijan `replicas`; `ignoreDifferences` si hiciera falta |

## Fase H: elasticidad, resiliencia y autoscaling de nodos

| Síntoma | Causa probable | Solución |
|---|---|---|
| No aparecen pods `Pending` | Requests demasiado bajos para el allocatable real | Calibrar con `kubectl describe node` (plan §2.2) |
| La CPU no sube con la carga | Créditos de t3 agotados en modo *standard* | `cpu_credits = "unlimited"` |
| CA no hace scale-down | Pods con almacenamiento local o PDB que bloquean | `--skip-nodes-with-local-storage=false`; revisar PDBs |
| El nodo terminado sigue como `NotReady` | `cloud-node-lifecycle` no activo en el CCM | Revisar controladores del CCM |
| Tokens `live` > 0 durante la prueba de ataque | Fallo de admisión o `LLM_GLOBAL_MODE` | Parar la demo; revisar la barrera 1 y 2 de ADR-0002 §6 |

## Fase I: Grafana Cloud

| Síntoma | Causa probable | Solución |
|---|---|---|
| Sin series en Grafana Cloud | Credenciales de Alloy no sincronizadas por ESO o destino mal configurado | `kubectl -n monitoring get externalsecret`; logs de Alloy |
| `err-mimir-max-series-per-user` o series descartadas | Se superan las ~10k series del free tier | Allowlists de métricas en `k8s-monitoring` |
| Datasource CloudWatch sin datos | Rol cross-account o external ID incorrectos | Revisar la trust policy; nombre de rol determinista |
| Trazas cortadas por servicio | No se propaga `traceparent` hacia el gateway o en NATS | Revisar la instrumentación en `agentlib` |

## Cierre y costo

| Síntoma | Causa probable | Solución |
|---|---|---|
| `cost-check.sh` falla tras `make down` | Quedan instancias, LBs, TGs, volúmenes, EIPs, ENIs o la VPC | Repetir `terraform destroy`; borrar a mano solo lo que liste el script y registrarlo |
| El lab sigue encendido horas después | Se olvidó el `down` | `lab-reaper.yml` lo destruye al superar `LAB_TTL_HOURS` (6 h) |
