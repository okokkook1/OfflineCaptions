param([string]$OutputDirectory='')
$ErrorActionPreference='Stop'
if(-not $OutputDirectory){$OutputDirectory=Join-Path (Split-Path $PSScriptRoot -Parent) 'build\benchmark'}
New-Item -ItemType Directory -Force $OutputDirectory | Out-Null
$voiceKey=Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens' | Where-Object {$_.PSChildName -like '*Yating*'} | Select-Object -First 1
if(-not $voiceKey){throw 'No installed Yating voice; no system settings will be changed.'}
$token=New-Object -ComObject SAPI.SpObjectToken
$token.SetId($voiceKey.Name,'',$false)
$voice=New-Object -ComObject SAPI.SpVoice
$voice.Voice=$token
$text='大家好，今天我們討論專案進度。明天上午九點開會，請準備測試報告，謝謝大家。'
$stream=New-Object -ComObject SAPI.SpFileStream
$stream.Format.Type=18
$stream.Open((Join-Path $OutputDirectory 'zh-synthetic.wav'),3,$false)
$voice.AudioOutputStream=$stream
$null=$voice.Speak($text,0)
$stream.Close()
[IO.File]::WriteAllText((Join-Path $OutputDirectory 'zh-synthetic.txt'),$text,[Text.UTF8Encoding]::new($false))
Write-Output 'Generated Mandarin fixture using installed voice; registry unchanged.'
$mixed='今天的會議討論 project schedule，請在 tomorrow morning 準備好 test report，謝謝大家。'
$mixedStream=New-Object -ComObject SAPI.SpFileStream
$mixedStream.Format.Type=18
$mixedStream.Open((Join-Path $OutputDirectory 'mixed-synthetic.wav'),3,$false)
$voice.AudioOutputStream=$mixedStream
$null=$voice.Speak($mixed,0)
$mixedStream.Close()
[IO.File]::WriteAllText((Join-Path $OutputDirectory 'mixed-synthetic.txt'),$mixed,[Text.UTF8Encoding]::new($false))
