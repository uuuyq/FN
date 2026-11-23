param([string]$Gradle = "$PSScriptRoot/gradlew.bat")
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$signingDirectory = Join-Path $projectRoot 'runtime/android-signing'
New-Item -ItemType Directory -Force $signingDirectory | Out-Null
$env:FNOTE_KEYSTORE = Join-Path $signingDirectory 'release.p12'
$passwordPath = Join-Path $signingDirectory 'password.txt'
if (!(Test-Path $env:FNOTE_KEYSTORE)) {
    if (Test-Path $passwordPath) { throw 'Found password without keystore. Restore the existing keystore before building.' }
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    [Convert]::ToBase64String($bytes) | Set-Content $passwordPath -NoNewline
    $env:FNOTE_STORE_PASSWORD = Get-Content $passwordPath -Raw
    & "$env:JAVA_HOME/bin/keytool.exe" -genkeypair -keystore $env:FNOTE_KEYSTORE -storetype PKCS12 -storepass:env FNOTE_STORE_PASSWORD -alias fnote -keyalg RSA -keysize 3072 -validity 10000 -dname 'CN=FNote'
    if ($LASTEXITCODE -ne 0) { throw 'Signing key generation failed' }
}
try {
    $env:FNOTE_STORE_PASSWORD = Get-Content $passwordPath -Raw
    Push-Location $PSScriptRoot
    & $Gradle --no-daemon assembleRelease
    if ($LASTEXITCODE -ne 0) { throw 'APK build failed' }
} finally {
    Pop-Location
    Remove-Item Env:FNOTE_STORE_PASSWORD -ErrorAction SilentlyContinue
}
