param([string]$OutputDirectory='')
$ErrorActionPreference='Stop'
if(-not $OutputDirectory){$OutputDirectory=Join-Path (Split-Path $PSScriptRoot -Parent) 'build\qa'}
New-Item -ItemType Directory -Force $OutputDirectory | Out-Null
Add-Type -AssemblyName System.Speech
$synth=New-Object System.Speech.Synthesis.SpeechSynthesizer
$format=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono)
$voices=$synth.GetInstalledVoices() | ForEach-Object {$_.VoiceInfo}
foreach($item in @(@{Language='en';Culture='en';Text='Hello everyone. Today we will discuss the project schedule. The meeting starts at nine tomorrow morning.'},@{Language='zh';Culture='zh';Text='大家好，今天我們討論專案進度。明天上午九點開會，謝謝大家。'})){
    $voice=$voices | Where-Object {$_.Culture.Name.StartsWith($item.Culture)} | Select-Object -First 1
    if($voice){$synth.SelectVoice($voice.Name);$path=Join-Path $OutputDirectory ($item.Language+'.wav');$synth.SetOutputToWaveFile($path,$format);$synth.Speak($item.Text);$synth.SetOutputToNull();Write-Output $path}
}
$synth.Dispose()
