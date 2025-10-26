{{/*
Expand the name of the chart.
*/}}
{{- define "transcript-create.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "transcript-create.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "transcript-create.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "transcript-create.labels" -}}
helm.sh/chart: {{ include "transcript-create.chart" . }}
{{ include "transcript-create.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "transcript-create.selectorLabels" -}}
app.kubernetes.io/name: {{ include "transcript-create.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
API specific labels
*/}}
{{- define "transcript-create.api.labels" -}}
{{ include "transcript-create.labels" . }}
app.kubernetes.io/component: api
{{- end }}

{{/*
API selector labels
*/}}
{{- define "transcript-create.api.selectorLabels" -}}
{{ include "transcript-create.selectorLabels" . }}
app.kubernetes.io/component: api
{{- end }}

{{/*
Worker specific labels
*/}}
{{- define "transcript-create.worker.labels" -}}
{{ include "transcript-create.labels" . }}
app.kubernetes.io/component: worker
{{- end }}

{{/*
Worker selector labels
*/}}
{{- define "transcript-create.worker.selectorLabels" -}}
{{ include "transcript-create.selectorLabels" . }}
app.kubernetes.io/component: worker
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "transcript-create.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "transcript-create.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Database URL - from external service or secret
*/}}
{{- define "transcript-create.databaseUrl" -}}
{{- if .Values.externalServices.database.enabled }}
{{- .Values.externalServices.database.url }}
{{- else }}
postgresql+psycopg://postgres:postgres@{{ include "transcript-create.fullname" . }}-postgresql:5432/transcripts
{{- end }}
{{- end }}

{{/*
Redis URL - from external service or internal
*/}}
{{- define "transcript-create.redisUrl" -}}
{{- if .Values.externalServices.redis.enabled }}
{{- .Values.externalServices.redis.url }}
{{- else }}
redis://{{ include "transcript-create.fullname" . }}-redis:6379/0
{{- end }}
{{- end }}

{{/*
OpenSearch URL - from external service or internal
*/}}
{{- define "transcript-create.opensearchUrl" -}}
{{- if .Values.externalServices.opensearch.enabled }}
{{- .Values.externalServices.opensearch.url }}
{{- else }}
http://{{ include "transcript-create.fullname" . }}-opensearch:9200
{{- end }}
{{- end }}

{{/*
Image pull secrets
*/}}
{{- define "transcript-create.imagePullSecrets" -}}
{{- if .Values.image.pullSecrets }}
imagePullSecrets:
{{- range .Values.image.pullSecrets }}
  - name: {{ . }}
{{- end }}
{{- end }}
{{- end }}

{{/*
GPU resource limits for worker
*/}}
{{- define "transcript-create.worker.gpuResources" -}}
{{- if .Values.worker.gpu.enabled }}
{{- if eq .Values.worker.gpu.type "nvidia" }}
nvidia.com/gpu: 1
{{- else if eq .Values.worker.gpu.type "amd" }}
amd.com/gpu: 1
{{- end }}
{{- end }}
{{- end }}

{{/*
Pod security context
*/}}
{{- define "transcript-create.podSecurityContext" -}}
{{- toYaml .Values.podSecurityContext }}
{{- end }}

{{/*
Container security context
*/}}
{{- define "transcript-create.securityContext" -}}
{{- toYaml .Values.securityContext }}
{{- end }}
