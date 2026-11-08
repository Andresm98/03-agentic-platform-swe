# Ejercicios: despliega tu contenedor en la plataforma

Subes una aplicación simple con su `Dockerfile`, abres un Pull Request y, cuando se aprueba, tu
contenedor recorre la arquitectura completa: CI, registry, GitOps, Kubernetes y balanceador.

## Pasos

1. Haz un fork del repositorio y crea tu rama a partir de `stage`.
2. Copia la carpeta de ejemplo con tu nombre y adáptala a tu proyecto:

   ```bash
   cp -r exercises/_ejemplo exercises/<tu-nombre>
   ```

3. Edita `exercises/<tu-nombre>/exercise.yaml` con tu usuario de GitHub, el puerto y una descripción.
4. Pruébalo en tu máquina (ver [`_ejemplo/README.md`](_ejemplo/README.md)).
5. Abre un Pull Request **hacia la rama `stage`**.

## Qué pasa después

| Etapa | Qué ocurre |
|---|---|
| Revisión de CI | Se valida tu carpeta, se construye la imagen, se escanea y se despliega en un cluster temporal para comprobar que responde. El instructor debe autorizar la primera ejecución |
| Revisión humana | El instructor lee tu código y tu `Dockerfile`, y aprueba el PR |
| Publicación | CI publica la imagen y actualiza la configuración GitOps en `stage` |
| Despliegue | Argo CD despliega tu contenedor en el namespace `stage` |
| Acceso | Mientras el laboratorio esté encendido: `http://<dirección-del-laboratorio>/s/<tu-nombre>/` |

## Reglas que comprueba CI

- **Solo tu carpeta:** el PR no puede modificar nada fuera de `exercises/<tu-nombre>/`.
- **Máximo 3 ejercicios** desplegados a la vez.
- **Nombre de la carpeta:** minúsculas, números y guiones, de 2 a 31 caracteres.
- **Archivos obligatorios:** `Dockerfile`, `exercise.yaml` y `README.md`.
- **`exercise.yaml`:** solo `owner`, `port` (1024–65535) y `description`.
- **`Dockerfile`:** imágenes base con versión fijada (nada de `latest`) y, en la etapa final, un `USER` numérico distinto de 0.
- **Sin secretos** ni enlaces simbólicos, y un máximo de 2 MB en la carpeta.

## Contrato de tu aplicación

- Escucha en el puerto declarado en `exercise.yaml`, en `0.0.0.0`.
- Responde `200` en `/healthz` (está viva) y en `/readyz` (puede recibir tráfico).
- Funciona con el sistema de archivos en solo lectura; solo puede escribir en `/tmp`.
- Se sirve bajo `/s/<tu-nombre>/`, pero tu aplicación recibe las rutas sin ese prefijo.
- Si devuelves HTML, usa enlaces relativos (`static/app.css`, no `/static/app.css`) y abre la URL con la barra final. Un enlace absoluto saldría de `/s/<tu-nombre>/` y daría 404.
- Opcional: `/metrics` en formato Prometheus.

## Acceso público y límites

Mientras el laboratorio esté encendido, **cualquiera puede ver tu aplicación desde Internet** en
`http://<dirección-del-laboratorio>/s/<tu-nombre>/`. La dirección cambia cada vez que se levanta el
laboratorio. Es HTTP sin cifrar y tiene límite de peticiones por IP, así que no publiques datos sensibles.

Tu contenedor dispone de 100m de CPU y 128 MiB de memoria. Puede recibir visitas, pero **no puede
iniciar conexiones hacia Internet** ni hacia otros servicios de la plataforma.
