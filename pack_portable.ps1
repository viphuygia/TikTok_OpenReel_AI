param(
    [string]$OutZip = ""
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path $PSScriptRoot).Path
if ($OutZip -eq "") {
    $OutZip = Join-Path $Root "TikTok_OpenReel_AI_Portable.zip"
}

$Stage = Join-Path $env:TEMP ("OpenReel_Stage_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $Stage -Force | Out-Null

try {
    Write-Host "[Pack] Dang gom Code + Tai nguyen + Model F5-TTS (bo qua projects/, venv/, node_modules/)..." -ForegroundColor Cyan

    foreach ($dirRel in @("scripts", ".agents", "assets", "06_assets_audio")) {
        $src = Join-Path $Root $dirRel
        if (Test-Path -LiteralPath $src) {
            robocopy $src (Join-Path $Stage $dirRel) /E /XD __pycache__ bin | Out-Null
        }
    }

    # Include F5-TTS model + vocab + reference templates (exclude venv and projects)
    $modelSrc = Join-Path $Root "03_voice_clone\model"
    if (Test-Path -LiteralPath $modelSrc) {
        robocopy $modelSrc (Join-Path $Stage "03_voice_clone\model") /E | Out-Null
    }
    foreach ($f in @("giong_mau.wav", "noi_dung_giong_mau.txt")) {
        $p = Join-Path $Root "03_voice_clone\$f"
        if (Test-Path -LiteralPath $p) { Copy-Item -LiteralPath $p -Destination (Join-Path $Stage "03_voice_clone\$f") -Force }
    }
    $voicesSrc = Join-Path $Root "03_voice_clone\voices"
    if (Test-Path -LiteralPath $voicesSrc) {
        robocopy $voicesSrc (Join-Path $Stage "03_voice_clone\voices") /E | Out-Null
    }

    # Include Remotion & HyperFrames source/configs without node_modules or workspace
    foreach ($np in @("remotion_studio", "hyperframes_studio")) {
        $ns = Join-Path $Root $np
        if (Test-Path -LiteralPath $ns) {
            robocopy $ns (Join-Path $Stage $np) /E /XD node_modules .remotion workspace public | Out-Null
        }
    }

    foreach ($rootFile in @("requirements.txt", "install.bat", "clone_new_channel.bat", "start_server_24_7.bat", "pack_portable.ps1", ".gitignore", "README.md")) {
        $rf = Join-Path $Root $rootFile
        if (Test-Path -LiteralPath $rf) { Copy-Item -LiteralPath $rf -Destination (Join-Path $Stage $rootFile) -Force }
    }

    # Create empty project/workspace skeleton
    foreach ($emptyDir in @("projects", "01_video_mau", "02_video_tho", "04_workspace", "remotion_studio\public\workspace")) {
        New-Item -ItemType Directory -Path (Join-Path $Stage $emptyDir) -Force | Out-Null
    }

    if (Test-Path -LiteralPath $OutZip) { Remove-Item -LiteralPath $OutZip -Force }
    Write-Host "[Pack] Dang nen thanh: $OutZip ..." -ForegroundColor Cyan
    Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $OutZip -CompressionLevel Optimal
    $sizeMb = [math]::Round((Get-Item -LiteralPath $OutZip).Length / 1MB, 1)
    Write-Host "[OK] Da dong goi xong: $OutZip ($sizeMb MB)" -ForegroundColor Green
} finally {
    if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction SilentlyContinue }
}
