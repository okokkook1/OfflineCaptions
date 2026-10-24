@echo off
setlocal
for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSROOT=%%i"
if not defined VSROOT exit /b 1
call "%VSROOT%\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
"%VSROOT%\MSBuild\Current\Bin\MSBuild.exe" "%~dp0..\native\Capture.vcxproj" /p:Configuration=Release /p:Platform=x64 /v:minimal /nologo
exit /b %errorlevel%
