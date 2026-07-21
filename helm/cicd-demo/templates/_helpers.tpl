{{/*
Reusable template snippets (helpers). Keeping names and labels defined ONCE here
means every template stays consistent — the DRY principle for Helm charts.
*/}}

{{/* The base app name, overridable via nameOverride. */}}
{{- define "cicd-demo.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
The fully-qualified resource name: "<release>-<chart>", unless the release name
already contains the chart name (avoids "cicd-demo-cicd-demo"). Truncated to the
63-char Kubernetes name limit.
*/}}
{{- define "cicd-demo.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* Full set of recommended labels, stamped on every object. */}}
{{- define "cicd-demo.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "cicd-demo.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels — the MINIMAL, STABLE set used to match pods to their Deployment
and Service. These must never change for a running release, so they exclude
version (which does change).
*/}}
{{- define "cicd-demo.selectorLabels" -}}
app.kubernetes.io/name: {{ include "cicd-demo.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* The ServiceAccount name to use (defaults to the fullname). */}}
{{- define "cicd-demo.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "cicd-demo.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}
