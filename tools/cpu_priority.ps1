# C16 (AUTOMATIONS.md): NinjaTrader above normal, Ollama below normal, so a heavy local model
# or a test tier can never starve the trading app. Process priority only - no settings, no
# registry. Dry run by default: prints what it would change. -Apply makes the change.
# Priority does not survive a restart of the process, so the owner's logon/every-15-min task
# (docs/C16_CPU_PRIORITY_DRAFT.md) re-applies it.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\cpu_priority.ps1 [-Apply]
param([switch]$Apply)

$want = [ordered]@{
    'NinjaTrader' = 'AboveNormal'
    'ollama'      = 'BelowNormal'
    'ollama app'  = 'BelowNormal'
}
foreach ($name in $want.Keys) {
    foreach ($p in @(Get-Process -Name $name -ErrorAction SilentlyContinue)) {
        $now = "$($p.PriorityClass)"
        if ($now -eq $want[$name]) { "ok      $name ($($p.Id)) $now"; continue }
        if ($Apply) {
            try { $p.PriorityClass = $want[$name]; "set     $name ($($p.Id)) $now -> $($want[$name])" }
            catch { "FAILED  $name ($($p.Id)): $($_.Exception.Message)" }
        } else { "would   $name ($($p.Id)) $now -> $($want[$name])" }
    }
}
