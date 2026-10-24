param([string]$Dotnet='', [string]$ModelRoot='', [switch]$SkipBuild)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
if (-not $Dotnet) {$Dotnet=Join-Path (Split-Path $projectRoot -Parent) '.tools\dotnet\dotnet.exe';if(-not(Test-Path $Dotnet)){$Dotnet=(Get-Command dotnet).Source}}
$env:DOTNET_CLI_TELEMETRY_OPTOUT='1'
$env:DOTNET_CLI_HOME=Join-Path $projectRoot 'build\dotnet-home'
if (-not $SkipBuild) {& "$PSScriptRoot\build.ps1" -Dotnet $Dotnet -SelfContained}
if (-not $ModelRoot) {$ModelRoot=Join-Path $projectRoot 'models'}
$portable=Join-Path $projectRoot 'dist\OfflineCaptions'
$python=Join-Path $portable 'runtime\python.exe'
if (-not(Test-Path $python)) {throw '請先執行 scripts\prepare-runtime.ps1'}
& $python backend\models.py check --root $ModelRoot
if ($LASTEXITCODE) {throw '離線模型不完整'}
New-Item -ItemType Directory -Force (Join-Path $portable 'models') | Out-Null
foreach($folder in @('sensevoice-small-int8','opus-en-zh')) {Copy-Item -LiteralPath (Join-Path $ModelRoot $folder) -Destination (Join-Path $portable 'models') -Recurse -Force}
$payload=Join-Path $projectRoot 'build\payload.zip'
& $python scripts\archive_release.py $portable $payload
if ($LASTEXITCODE) {throw '壓縮失敗'}
Copy-Item $payload dist\OfflineCaptions-Windows-x64.zip -Force
& $Dotnet publish installer\Installer.csproj -c Release -r win-x64 --self-contained true -o dist\Setup --nologo --source https://api.nuget.org/v3/index.json
if ($LASTEXITCODE) {throw '安裝程式編譯失敗'}
Copy-Item dist\Setup\OfflineCaptions-Setup.exe dist\OfflineCaptions-Setup.exe -Force
Get-FileHash dist\OfflineCaptions-Setup.exe,dist\OfflineCaptions-Windows-x64.zip -Algorithm SHA256 | Format-Table -AutoSize
