{{/*
MAYA — the refusals this chart makes at template time.

A chart that renders is a chart somebody installs, so the place to refuse a
configuration that cannot be safe is HERE, before anything reaches a cluster.
Each `fail` below replaces a deployment that would have run and been quietly
wrong.
*/}}

{{- define "maya.fullname" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "maya.labels" -}}
app.kubernetes.io/name: {{ include "maya.fullname" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
The three secrets that have no default.

A chart shipping a working signing key ships a key everybody has, and a
deployment that RUNS is one nobody goes back and fixes. So this fails to
render, which somebody has to read.
*/}}
{{- define "maya.requireSecrets" -}}
{{- if not .Values.secrets.databaseUrlSecret -}}
{{- fail "secrets.databaseUrlSecret is required. Name a Secret holding the database URL; this chart will not template a literal, because a literal ends up in `helm get values`, in the release history, and in whatever ships the values file into the cluster. Connect as a role that owns nothing and is not a superuser — see deploy/postgres-init.sql." -}}
{{- end -}}
{{- if not .Values.secrets.sessionSecret -}}
{{- fail "secrets.sessionSecret is required. Without it the session cookie is signed with the published default, and anybody with a copy of this repository can forge a signed-in session as any user, including admin, with no password." -}}
{{- end -}}
{{- if not .Values.secrets.warrantSigningKeySecret -}}
{{- fail "secrets.warrantSigningKeySecret is required. Per-audience warrant keys are DERIVED from this root, so a published root is every engine's key at once." -}}
{{- end -}}
{{- end -}}

{{/*
An anchor store that only one replica can write to.

ReadWriteOnce with replicaCount > 1 gives a cluster where one pod holds the
volume and the others cannot anchor. Anchoring then happens on one pod out of
three, intermittently, and the readiness report says the chain is anchored —
which is worse than no anchoring at all, because somebody believes it.
*/}}
{{- define "maya.requireWorm" -}}
{{- if .Values.worm.enabled -}}
{{- if and (gt (int .Values.replicaCount) 1) (eq .Values.worm.accessMode "ReadWriteOnce") -}}
{{- fail "worm.accessMode ReadWriteOnce with replicaCount > 1: one pod would hold the anchor volume and the others could not anchor. Anchoring would then happen intermittently on one pod while the readiness report said the chain was anchored, which is worse than not anchoring. Use ReadWriteMany, or set replicaCount to 1." -}}
{{- end -}}
{{- else -}}
{{- fail "worm.enabled is false. The WORM anchor store is the only check on the evidence chain that somebody holding the database cannot simply satisfy; without it, tamper evidence rests on the chain agreeing with itself, which a rewritten chain does perfectly. If this deployment genuinely has no durable volume, say so in the readiness report rather than here." -}}
{{- end -}}
{{- end -}}
