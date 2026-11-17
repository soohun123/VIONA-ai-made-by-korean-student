param([switch]$Prepare,[switch]$Installer)
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
& .\download_prerequisites.ps1
$py=Join-Path $PSScriptRoot '.build-venv\Scripts\python.exe'
& $py update_tools.py init
if($LASTEXITCODE){throw 'Update helper build failed'}
& $py update_tools.py next-version
if($LASTEXITCODE){throw 'Version preparation failed'}
if ($Prepare) { & $py prepare.py --include-qwen; if($LASTEXITCODE){throw 'Prepare failed'} }
& $py -m PyInstaller --noconfirm --clean --onedir --windowed --name NOVERA_AI_Desktop --icon assets\novera.ico --paths src --add-data 'assets;assets' --add-data 'licenses;licenses' --add-data '..\NovaBrain\NovaBrain_LLM_v8\media-runtime;media-runtime' --add-binary '..\NovaBrain\NovaBrain_LLM_v8\.venv\Lib\site-packages\nvidia\cublas\bin\*.dll;.' --add-binary '..\NovaBrain\NovaBrain_LLM_v8\.venv\Lib\site-packages\nvidia\cuda_runtime\bin\*.dll;.' --collect-all webview --collect-all pythonnet --collect-all clr_loader --collect-all llama_cpp --collect-all authlib --hidden-import gguf_metadata --hidden-import generation_resources --hidden-import PIL.Image --exclude-module torch --exclude-module transformers --exclude-module PyQt5 --exclude-module PyQt6 src\desktop.py
if($LASTEXITCODE){throw 'PyInstaller failed'}
& $py update_tools.py stage
if($LASTEXITCODE){throw 'Version staging failed'}
$version=(Get-Content -LiteralPath VERSION.txt -Raw).Trim()
$iss=Get-Content -LiteralPath installer.iss -Raw
$iss=[regex]::Replace($iss,'(?m)^AppVersion=.*$',('AppVersion='+$version))
Set-Content -LiteralPath installer.iss -Value $iss -Encoding utf8
$iscc='C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
if($Installer -or $Prepare){
  & $iscc installer.iss
  if($LASTEXITCODE){throw 'Installer compilation failed'}
}
& $py -m pip freeze | Set-Content -Encoding utf8 build-requirements.lock.txt

& $py update_tools.py publish
if($LASTEXITCODE){throw 'Signed update publication failed'}
