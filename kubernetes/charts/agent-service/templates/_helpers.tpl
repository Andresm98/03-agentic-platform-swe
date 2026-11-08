{{- define "agent-service.name" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "agent-service.selectorLabels" -}}
app.kubernetes.io/name: {{ include "agent-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "agent-service.labels" -}}
{{ include "agent-service.selectorLabels" . }}
app.kubernetes.io/part-of: agentic-fleet
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "agent-service.secretName" -}}
{{ include "agent-service.name" . }}-secrets
{{- end -}}
