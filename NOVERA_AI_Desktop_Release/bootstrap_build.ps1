$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
& .\download_prerequisites.ps1
$base=Join-Path $PSScriptRoot '..\NovaBrain\Python311\python.exe'
if(-not (Test-Path -LiteralPath $base)){throw 'Python 3.11 is required. Set $base to its python.exe.'}
if(-not (Test-Path -LiteralPath '.build-venv\Scripts\python.exe')){& $base -m venv .build-venv}
$py=Join-Path $PSScriptRoot '.build-venv\Scripts\python.exe'
$wheel=Join-Path $PSScriptRoot '..\NovaBrain\setup\gpu-wheels\llama_cpp_python-0.3.36-py3-none-win_amd64.whl'
if(-not (Test-Path -LiteralPath $wheel)){throw 'The verified Windows llama-cpp-python wheel is required.'}
if((Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToLower() -ne '7086b98420cf9cca5e3f14181edc4332038bfb0a0e380370a693806bb527911f'){throw 'Wheel checksum mismatch'}
& $py -m pip install pywebview==6.2.1 pyinstaller==6.22.3 psutil==7.2.2 pillow==13.0.0 numpy==2.4.6 authlib==1.9.6 cryptography==50.0.2 $wheel
if($LASTEXITCODE){throw 'Build dependency installation failed'}
& .\build.ps1 -Prepare
