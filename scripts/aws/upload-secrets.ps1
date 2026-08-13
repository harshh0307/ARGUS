param(
    [string]$Region = "us-east-1",
    [string]$Prefix = "/argus",
    [string]$EnvFile = "$PSScriptRoot\..\..\.env"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) {
    Write-Error ".env not found at $EnvFile"
}

$secretKeys = @(
    "GITHUB_TOKEN",
    "GITHUB_APP_ID",
    "GITHUB_APP_PRIVATE_KEY",
    "GITHUB_INSTALL_ID",
    "WEBHOOK_SECRET",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENROUTER_MODEL",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "EMBEDDING_API_KEY",
    "EMBEDDING_BASE_URL",
    "EMBEDDING_MODEL",
    "FIX_MAX_ATTEMPTS"
)

$envValues = @{}
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match "^([A-Z0-9_]+)=(.*)$") {
        $envValues[$Matches[1]] = $Matches[2].Trim('"')
    }
}

foreach ($key in $secretKeys) {
    if (-not $envValues.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($envValues[$key])) {
        Write-Host "SKIP  $key (empty or missing in .env)"
        continue
    }
    $name = "$Prefix/$key"
    $value = $envValues[$key]
    Write-Host "SET   $name"
    aws ssm put-parameter --region $Region --name $name --type SecureString --value $value --overwrite | Out-Null
}

Write-Host "Done. Prefix: $Prefix"
