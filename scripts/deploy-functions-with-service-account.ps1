param(
    [Parameter(Mandatory = $true)]
    [string]$CredentialPath,

    [string]$Project = "pickdreamtest"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $CredentialPath)) {
    throw "Service account key file not found: $CredentialPath"
}

$resolvedCredential = (Resolve-Path -LiteralPath $CredentialPath).Path
$env:GOOGLE_APPLICATION_CREDENTIALS = $resolvedCredential
$env:GOOGLE_CLOUD_PROJECT = $Project
$env:GCLOUD_PROJECT = $Project
if (-not $env:FUNCTIONS_DISCOVERY_TIMEOUT) {
    $env:FUNCTIONS_DISCOVERY_TIMEOUT = "60"
}

Write-Host "Using service account key: $resolvedCredential"
Write-Host "Deploying Firebase Functions to project: $Project"

firebase deploy --only functions --project $Project
