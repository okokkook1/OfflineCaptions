param([string]$HostPython='python', [switch]$IncludeConverter)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$runtimePath=Join-Path $projectRoot 'dist\OfflineCaptions\runtime'
$archivePath=Join-Path $projectRoot 'build\python-3.11.9-embed-amd64.zip'
New-Item -ItemType Directory -Force $runtimePath,(Split-Path $archivePath -Parent) | Out-Null
if (-not (Test-Path $archivePath)) {Invoke-WebRequest 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' -OutFile $archivePath}
Expand-Archive -LiteralPath $archivePath -DestinationPath $runtimePath -Force
@('python311.zip','.','Lib\site-packages','..\backend','import site') | Set-Content -Encoding ascii (Join-Path $runtimePath 'python311._pth')
$requirements=Join-Path $projectRoot 'backend\requirements.lock.txt'
if(-not(Test-Path $requirements)){$requirements=Join-Path $projectRoot 'backend\requirements.txt'}
& $HostPython -m pip install --disable-pip-version-check --only-binary=:all: --target (Join-Path $runtimePath 'Lib\site-packages') -r $requirements
if ($LASTEXITCODE) {throw 'Python 執行環境依賴安裝失敗'}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vsInstall=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$crtPath=Get-ChildItem "$vsInstall\VC\Redist\MSVC\*\x64\Microsoft.VC143.CRT" -Directory | Sort-Object FullName -Descending | Select-Object -First 1
if(-not $crtPath){throw '找不到可轉散佈的 Microsoft VC143 CRT；請安裝 C++ Build Tools'}
Copy-Item (Join-Path $crtPath.FullName '*.dll') $runtimePath -Force
if ($IncludeConverter) {
    & $HostPython -m pip install --disable-pip-version-check --upgrade --only-binary=:all: --target (Join-Path $runtimePath 'Lib\site-packages') transformers==4.57.1 torch==2.6.0
    if ($LASTEXITCODE) {throw '模型轉換工具安裝失敗'}
}
& (Join-Path $runtimePath 'python.exe') -c 'import numpy, ctranslate2, faster_whisper, sentencepiece, opencc, sherpa_onnx; print("Bundled Python runtime: OK (SenseVoice)")'
if ($LASTEXITCODE) {throw '內附執行環境驗證失敗'}
