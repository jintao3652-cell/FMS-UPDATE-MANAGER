# MSI Code Signing

The MSI installer can be Authenticode-signed with `installer/sign_msi.bat`. The
script reads the certificate path and password from environment variables so
nothing sensitive ends up in the repo.

## Environment variables

| Variable        | Required | Default                              | Notes                                        |
|-----------------|----------|--------------------------------------|----------------------------------------------|
| `FMS_SIGN_PFX`  | yes      | —                                    | Absolute path to your `.pfx` certificate     |
| `FMS_SIGN_PWD`  | yes      | —                                    | Password for the `.pfx`                      |
| `FMS_SIGN_TSA`  | no       | `http://timestamp.digicert.com`      | RFC3161 timestamp server                     |
| `FMS_SIGNTOOL`  | no       | `signtool.exe` (must be on `PATH`)   | Absolute path to a specific `signtool.exe`   |

`signtool.exe` ships with the Windows SDK (e.g.
`C:\Program Files (x86)\Windows Kits\10\bin\<sdk-version>\x64\signtool.exe`).
Either add that folder to `PATH` or set `FMS_SIGNTOOL` to its full path.

## Usage

```bat
set FMS_SIGN_PFX=C:\path\to\fms-codesign.pfx
set FMS_SIGN_PWD=your-pfx-password
installer\sign_msi.bat dist\FMS_UPDATE_MANAGER_Installer.msi
```

The script signs with SHA-256 + RFC3161 timestamp, then verifies the signature
(`signtool verify /pa /v`). Exit code 0 = success.

You can also call it on the unpacked `.exe` produced by PyInstaller before
WiX wraps it into the MSI — passing an EXE works the same way.

## Wiring it into your build

Add a line to the end of your build pipeline:

```bat
REM after WiX produces the MSI
installer\sign_msi.bat dist\FMS_UPDATE_MANAGER_Installer.msi || exit /b 1
```

If you build through PowerShell or another driver, just shell out to the bat
file the same way.

## Pinning the trusted certificate (#41)

By default the client will accept *any* Authenticode-valid signature on the
auto-update MSI. To prevent an attacker who controls a different (still
trusted) CA-issued certificate from impersonating a release, the client
verifies the signer thumbprint against the env var `FMS_TRUSTED_CERT_THUMBPRINTS`.

To find your certificate's SHA1 thumbprint:

```powershell
Get-AuthenticodeSignature -FilePath dist\FMS_UPDATE_MANAGER\FMS_UPDATE_MANAGER.exe |
  Select-Object -ExpandProperty SignerCertificate |
  Select-Object Subject, Thumbprint
```

Set it for the **client** runtime — typically baked into the bundled config
or the user's environment. Multiple thumbprints are comma-separated to make
key rollover possible (have both old and new valid for a short overlap):

```bat
set FMS_TRUSTED_CERT_THUMBPRINTS=0123456789ABCDEF...,FEDCBA9876543210...
```

If `FMS_TRUSTED_CERT_THUMBPRINTS` is unset/empty, the client logs the
observed thumbprint but does **not** reject signed-by-anyone MSIs. For
production builds you should set it.

## One-shot signed build

Prefer the wrapper [build_signed.bat](build_signed.bat) for full builds:

```bat
set FMS_SIGN_PFX=C:\path\to\fms-codesign.pfx
set FMS_SIGN_PWD=your-pfx-password
installer\build_signed.bat              REM release (FMS_UPDATE_MANAGER.spec)
installer\build_signed.bat beta         REM beta    (FMS_UPDATE_MANAGER_beta.spec)
```

## Self-signed certificate (dev / pipeline smoke test)

If you don't have a CA-issued code-signing certificate yet, generate a
self-signed one to exercise the pipeline end-to-end. End users will still
see "Unknown publisher" SmartScreen warnings, so this is **not** a
substitute for a real cert in a public release.

```powershell
# from the project root (PowerShell)
.\installer\make_selfsigned_cert.ps1 -OutDir .\.secrets -CurrentUserStore
# It will prompt for a password; remember it — it becomes FMS_SIGN_PWD.

$env:FMS_SIGN_PFX = "$PWD\.secrets\fms_selfsigned.pfx"
$env:FMS_SIGN_PWD = "<the password you entered>"
.\installer\build_signed.bat
```

Optional: locally trust the self-signed cert so SmartScreen treats your
own installer as known (admin PowerShell):

```powershell
Import-Certificate -FilePath .\.secrets\fms_selfsigned.pfx `
  -CertStoreLocation Cert:\LocalMachine\TrustedPublisher
Import-Certificate -FilePath .\.secrets\fms_selfsigned.pfx `
  -CertStoreLocation Cert:\LocalMachine\Root
```

For a real release, replace `FMS_SIGN_PFX` with a cert from a public CA
(DigiCert / SSL.com / Sectigo / Certum) and ideally also pin its
thumbprint via `FMS_TRUSTED_CERT_THUMBPRINTS` (see above).

The wrapper runs the full pipeline:

1. PyInstaller (`--clean`) builds the EXE
2. `sign_msi.bat` signs the EXE (Authenticode reputation accumulates faster
   when both EXE and MSI are signed — set `FMS_SKIP_SIGN_EXE=1` to skip)
3. WiX builds the MSI; product version comes from `FMS_APP_VERSION` (default
   `1.0.5`), passed via `-d ProductVersion=...`
4. `sign_msi.bat` signs the MSI (set `FMS_SKIP_SIGN_MSI=1` to skip)

Extra env vars used only by `build_signed.bat`:

| Variable           | Default     | Notes                                            |
|--------------------|-------------|--------------------------------------------------|
| `FMS_WIX_BIN`      | `wix`       | Path to WiX v4 `wix.exe` if not on `PATH`        |
| `FMS_APP_VERSION`  | `1.0.5`     | Stamped into MSI via `Version="$(var.ProductVersion)"` in `*.wxs` |
| `FMS_SKIP_SIGN_EXE`| —           | Set to `1` to skip EXE signing                   |
| `FMS_SKIP_SIGN_MSI`| —           | Set to `1` to skip MSI signing                   |
