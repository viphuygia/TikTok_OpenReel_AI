param(
    [switch]$ForceDeps
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepoUrl = "https://github.com/viphuygia/TikTok_OpenReel_AI.git"
$CachePath = Join-Path $Root ".update_cache.json"

function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[ OK ] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }

function Get-FileSha256($path) {
    if (-not (Test-Path -LiteralPath $path)) { return "" }
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
}

Write-Host "=====================================================" -ForegroundColor Magenta
Write-Host "  TikTok OpenReel AI - Delta Fast Updater (5-15s)" -ForegroundColor Magenta
Write-Host "=====================================================" -ForegroundColor Magenta

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Warn "Khong tim thay 'git' trong PATH. Vui long cai Git for Windows hoac chay install.bat."
    exit 1
}

Push-Location $Root
try {
    # 1. Ensure Git repo is connected to origin
    if (-not (Test-Path -LiteralPath (Join-Path $Root ".git"))) {
        Write-Info "Khoi tao Git tracking cho thu muc hien tai..."
        git init -b main | Out-Null
        git remote add origin $RepoUrl
    } else {
        $curOrigin = (git remote get-url origin 2>$null)
        if (-not $curOrigin) {
            git remote add origin $RepoUrl
        }
    }

    # 2. Fetch latest commit & fast-sync code without touching user data
    Write-Info "Dang kiem tra ban cap nhat tu GitHub..."
    git fetch origin main --prune
    $oldHead = (git rev-parse HEAD 2>$null)
    $newHead = (git rev-parse origin/main 2>$null)

    if ($oldHead -and $newHead -and ($oldHead -eq $newHead) -and (-not $ForceDeps)) {
        Write-Ok "Ma nguon da o phien ban moi nhat ($($newHead.Substring(0,7)))."
    } else {
        if ($oldHead) {
            Write-Info "Cap nhat code: $($oldHead.Substring(0,7)) -> $($newHead.Substring(0,7))"
        } else {
            Write-Info "Dong bo code lan dau tu origin/main ($($newHead.Substring(0,7)))..."
        }
        git reset --hard origin/main

        # Clean obsolete tracked/untracked code files while strictly preserving user data & local models
        git clean -fd `
            -e "projects/" `
            -e "04_workspace/" `
            -e "03_voice_clone/" `
            -e "01_video_mau/" `
            -e "02_video_tho/" `
            -e "channel_profile.json" `
            -e "style_dna.json" `
            -e "phong_cach_kenh.md" `
            -e "config.json" `
            -e "assets/bin/" `
            -e ".update_cache.json" `
            -e "remotion_studio/node_modules/" `
            -e "hyperframes_studio/node_modules/" `
            -e "remotion_studio/public/workspace/"
        Write-Ok "Da cap nhat code & loai bo file cu khong con dung."
    }

    # 3. Load previous dependency hash cache
    $prevCache = @{}
    if (Test-Path -LiteralPath $CachePath) {
        try {
            $raw = Get-Content -LiteralPath $CachePath -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($p in $raw.PSObject.Properties) {
                $prevCache[$p.Name] = [string]$p.Value
            }
        } catch {}
    }

    # 4. Check Python venv & requirements.txt delta
    $VenvPy = Join-Path $Root "03_voice_clone\venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $VenvPy)) {
        Write-Warn "Chua co Python venv -> Dang goi installer.ps1..."
        & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\installer.ps1")
    } else {
        $reqFile = Join-Path $Root "requirements.txt"
        $reqHash = Get-FileSha256 $reqFile
        if ($ForceDeps -or ($reqHash -and $reqHash -ne $prevCache["requirements_sha256"])) {
            Write-Info "requirements.txt co thay doi -> Dang cap nhat thu vien Python..."
            & $VenvPy -m pip install -r $reqFile
            Write-Ok "Da cap nhat thu vien Python."
        } else {
            Write-Ok "Python packages khong doi -> Bo qua pip install."
        }
    }

    # 5. Check Node package.json delta for remotion_studio & hyperframes_studio
    $nodeHashes = @{}
    foreach ($nodeProj in @("remotion_studio", "hyperframes_studio")) {
        $npDir = Join-Path $Root $nodeProj
        $pkgJson = Join-Path $npDir "package.json"
        $nmDir = Join-Path $npDir "node_modules"
        $pkgHash = Get-FileSha256 $pkgJson
        $cacheKey = "${nodeProj}_pkg_sha256"
        $nodeHashes[$cacheKey] = $pkgHash
        if ((Test-Path -LiteralPath $pkgJson) -and ($ForceDeps -or (-not (Test-Path -LiteralPath $nmDir)) -or ($pkgHash -ne $prevCache[$cacheKey]))) {
            Write-Info "$nodeProj/package.json co thay doi -> Dang chay npm install..."
            Push-Location $npDir
            npm install --no-audit --no-fund
            Pop-Location
            Write-Ok "Da cap nhat $nodeProj/node_modules."
        } else {
            Write-Ok "$nodeProj packages khong doi -> Bo qua npm install."
        }
    }

    # 6. Delta sync audio/visual assets & prune orphan files in remotion_studio/public/assets
    if (Test-Path -LiteralPath $VenvPy) {
        Write-Info "Dong bo SFX tinh te & tai nguyen delta..."
        & $VenvPy (Join-Path $Root "scripts\generate_audio_assets.py") | Out-Null
        & $VenvPy (Join-Path $Root "scripts\setup_assets.py") | Out-Null
        foreach ($sub in @("fonts", "stickers", "emojis", "animated_stickers", "lottie_stickers", "overlays")) {
            $srcSub = Join-Path $Root "assets\$sub"
            $dstSub = Join-Path $Root "remotion_studio\public\assets\$sub"
            if ((Test-Path -LiteralPath $srcSub) -and (Test-Path -LiteralPath $dstSub)) {
                $srcNames = @{}
                Get-ChildItem -LiteralPath $srcSub -File | ForEach-Object { $srcNames[$_.Name] = $true }
                Get-ChildItem -LiteralPath $dstSub -File | ForEach-Object {
                    if (-not $srcNames.ContainsKey($_.Name)) {
                        Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
                    }
                }
            }
        }
        Write-Ok "Da dong bo tai nguyen va don file thua."
    }

    # 7. Save updated cache
    $newCache = @{
        head_commit = $newHead
        requirements_sha256 = (Get-FileSha256 (Join-Path $Root "requirements.txt"))
        remotion_studio_pkg_sha256 = $nodeHashes["remotion_studio_pkg_sha256"]
        hyperframes_studio_pkg_sha256 = $nodeHashes["hyperframes_studio_pkg_sha256"]
        updated_at = (Get-Date).ToString("s")
    }
    $newCache | ConvertTo-Json | Set-Content -LiteralPath $CachePath -Encoding UTF8

    Write-Host ""
    Write-Ok "CAP NHAT HOAN TAT! Du lieu projects/ & giong mau cua ban duoc giu nguyen 100%."
    Write-Host "Hay chay start_web.bat de mo lai giao dien." -ForegroundColor Cyan
} finally {
    Pop-Location
}
