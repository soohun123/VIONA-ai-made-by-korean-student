$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Path prerequisites -Force | Out-Null
$runtime=Join-Path $PSScriptRoot 'prerequisites\MicrosoftEdgeWebView2RuntimeInstallerX64.exe'
if(-not (Test-Path -LiteralPath $runtime)){
    Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/?linkid=2124701' -OutFile $runtime
}
$signature=Get-AuthenticodeSignature -LiteralPath $runtime
if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Microsoft Corporation*'){
    throw 'Microsoft Runtime signature validation failed; file will not be executed or packaged.'
}
Write-Output ('Microsoft Runtime verified: '+(Get-FileHash -LiteralPath $runtime -Algorithm SHA256).Hash)
