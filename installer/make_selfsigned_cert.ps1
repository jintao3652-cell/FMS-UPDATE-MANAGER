# Generate a self-signed code-signing certificate for local CI / verifying
# the build_signed.bat pipeline end-to-end. End users will still see
# "Unknown publisher" SmartScreen warnings because the cert is not chained
# to a trusted CA. Replace with a real CA-issued cert before public release.
#
# Usage (in an elevated PowerShell, or with -CurrentUserStore):
#   .\make_selfsigned_cert.ps1 -OutDir D:\HugoMoveData\User\16832\Desktop\FMS UPDATE MANAGER\.secrets
#   $env:FMS_SIGN_PFX = "...\.secrets\fms_selfsigned.pfx"
#   $env:FMS_SIGN_PWD = "<the password you entered>"
#   cd ..; .\installer\build_signed.bat

[CmdletBinding()]
param(
    [string]$Subject = "CN=FMS Update Manager (self-signed)",
    [string]$OutDir = ".\.secrets",
    [string]$PfxName = "fms_selfsigned.pfx",
    [int]$YearsValid = 3,
    [switch]$CurrentUserStore
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir | Out-Null
}

$storeLocation = if ($CurrentUserStore) { "Cert:\CurrentUser\My" } else { "Cert:\LocalMachine\My" }
Write-Host "[make_cert] generating self-signed code-signing cert in $storeLocation ..."

$cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject $Subject `
    -KeyAlgorithm RSA `
    -KeyLength 3072 `
    -HashAlgorithm SHA256 `
    -CertStoreLocation $storeLocation `
    -NotAfter (Get-Date).AddYears($YearsValid) `
    -KeyExportPolicy Exportable

Write-Host ("[make_cert] thumbprint : {0}" -f $cert.Thumbprint)
Write-Host ("[make_cert] valid until: {0}" -f $cert.NotAfter)

$pfxPath = Join-Path (Resolve-Path $OutDir) $PfxName

$pwd = Read-Host "Enter password to protect the .pfx (will be needed as FMS_SIGN_PWD)" -AsSecureString
Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password $pwd | Out-Null

Write-Host ""
Write-Host "[make_cert] DONE"
Write-Host ("[make_cert] pfx file  : {0}" -f $pfxPath)
Write-Host ""
Write-Host "Next steps:"
Write-Host ('  $env:FMS_SIGN_PFX = "{0}"' -f $pfxPath)
Write-Host '  $env:FMS_SIGN_PWD = "<the password you just entered>"'
Write-Host "  .\installer\build_signed.bat"
Write-Host ""
Write-Host "Optional: trust this cert locally so SmartScreen treats it as known:"
Write-Host ("  Import-Certificate -FilePath '{0}' -CertStoreLocation Cert:\LocalMachine\TrustedPublisher" -f $pfxPath)
Write-Host ("  Import-Certificate -FilePath '{0}' -CertStoreLocation Cert:\LocalMachine\Root" -f $pfxPath)
