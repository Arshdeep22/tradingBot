# ─────────────────────────────────────────────────────────────────────────────
# Autonomous Optimizer Agent — SAP AI Core credentials + model selection
# ─────────────────────────────────────────────────────────────────────────────

$env:AICORE_AUTH_URL       = "https://private-cloud-agent-dev-eu12-155585.authentication.eu12.hana.ondemand.com"
$env:AICORE_API_URL        = "https://api.ai.intprod-eu12.eu-central-1.aws.ml.hana.ondemand.com"
$env:AICORE_CLIENT_ID      = "sb-9f2caf5c-fe42-4c21-8803-42a808cc70a0!b1606330|xsuaa_std!b318061"
$env:AICORE_CLIENT_SECRET  = '9cea8ca0-03d0-4fef-a818-5b23c376f875$tYqwr4kmgPzDHoVqX0GC_qNxvTRCHh1IjU0wxNrmttg='
$env:AICORE_RESOURCE_GROUP = "default"

# Model — pick any RUNNING foundation model. Common choices:
#   anthropic--claude-4.8-opus       (newest, heavily rate-limited)
#   anthropic--claude-4.7-opus       (recommended — same tier, better throughput)
#   anthropic--claude-4.6-opus
#   anthropic--claude-4.5-sonnet
#   anthropic--claude-4.5-haiku      (fastest / cheapest)
$env:AICORE_MODEL = "anthropic--claude-4.7-opus"

# Unbuffered Python stdout → log lines appear IMMEDIATELY, not in bursts.
$env:PYTHONUNBUFFERED = "1"

Set-Location "c:\Users\Arshdeep singh\Downloads\TradingBot\tradingBot"

$logFile = "logs/agent_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
New-Item -ItemType Directory -Force -Path "logs" | Out-Null

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " Autonomous Optimizer Agent " -ForegroundColor Cyan
Write-Host " Branch: main  (agent commits directly here)" -ForegroundColor Cyan
Write-Host " Model:  $env:AICORE_MODEL" -ForegroundColor Cyan
Write-Host " Log:    $logFile" -ForegroundColor Cyan
Write-Host " Ctrl+C to stop." -ForegroundColor Yellow
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

# `-u` + PYTHONUNBUFFERED = live stdout. Tee-Object splits to console + logfile.
py -3.12 -u -m autonomous_optimizer 2>&1 | Tee-Object -FilePath $logFile