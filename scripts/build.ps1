param([string]$Dotnet = "", [switch]$SelfContained)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
if (-not $Dotnet) {
    $localSdk=Join-Path (Split-Path $projectRoot -Parent) '.tools\dotnet\dotnet.exe'
    if (Test-Path $localSdk) {$Dotnet=$localSdk} else {$Dotnet=(Get-Command dotnet -ErrorAction Stop).Source}
}
$env:DOTNET_CLI_TELEMETRY_OPTOUT='1'
$env:DOTNET_CLI_HOME=Join-Path $projectRoot 'build\dotnet-home'
cmd.exe /c scripts\build-native.cmd
if ($LASTEXITCODE) {throw '原生收音模組編譯失敗。需要 Visual Studio 2022 C++ Build Tools 與 Windows 11 SDK。'}
$publishArgs=@('publish','app\OfflineCaptions.csproj','-c','Release','-r','win-x64','-o','dist\OfflineCaptions','--nologo','--source','https://api.nuget.org/v3/index.json')
if ($SelfContained) {$publishArgs+=@('--self-contained','true')} else {$publishArgs+=@('--self-contained','false')}
& $Dotnet @publishArgs
if ($LASTEXITCODE) {throw '桌面程式編譯失敗'}
Copy-Item README.md,THIRD-PARTY-NOTICES.md dist\OfflineCaptions
if(Test-Path VALIDATION.md){Copy-Item VALIDATION.md dist\OfflineCaptions}
if(Test-Path licenses){Copy-Item licenses -Destination dist\OfflineCaptions -Recurse -Force}
Write-Output '桌面程式位於 dist\OfflineCaptions'
