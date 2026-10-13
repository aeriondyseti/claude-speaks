# Reads UTF-8 text from stdin and speaks it with Windows SAPI.
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$text = [Console]::In.ReadToEnd()
if (-not $text.Trim()) { exit }

Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($env:CLAUDE_SPEAKS_VOICE) { $synth.SelectVoice($env:CLAUDE_SPEAKS_VOICE) }
$synth.Rate = if ($env:CLAUDE_SPEAKS_RATE) { [int]$env:CLAUDE_SPEAKS_RATE } else { 1 }
$synth.Speak($text)
