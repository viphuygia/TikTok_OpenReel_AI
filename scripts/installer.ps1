param(
    [string]$TargetDir = "",
    [string]$CloneTo = "",
    [int]$Port = 8000,
    [switch]$ForceVenv
)

$ErrorActionPreference = "Stop"
$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Write-Info([string]$msg) {
    Write-Host "[OpenReel AI] $msg" -ForegroundColor Cyan
}

function Write-Ok([string]$msg) {
    Write-Host "[OK] $msg" -ForegroundColor Green
}

function Ensure-Directory([string]$dirPath) {
    if (-not (Test-Path -LiteralPath $dirPath)) {
        New-Item -ItemType Directory -Path $dirPath -Force | Out-Null
    }
}

function Ensure-Junction([string]$linkPath, [string]$targetPath) {
    if (-not (Test-Path -LiteralPath $targetPath)) {
        return
    }
    if (Test-Path -LiteralPath $linkPath) {
        $item = Get-Item -LiteralPath $linkPath -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            return
        }
        $hasChildren = (Get-ChildItem -LiteralPath $linkPath -Force | Measure-Object).Count -gt 0
        if ($hasChildren) {
            Write-Info "Bo qua tao Junction vi thu muc thuc co du lieu da ton tai: $linkPath"
            return
        }
        Remove-Item -LiteralPath $linkPath -Force
    }
    Ensure-Directory (Split-Path -Parent $linkPath)
    $cmdLine = "mklink /J `"$linkPath`" `"$targetPath`""
    cmd /c $cmdLine | Out-Null
    if (-not (Test-Path -LiteralPath $linkPath)) {
        throw "Khong the tao Windows Junction: $linkPath -> $targetPath"
    }
    Write-Ok "Junction: $linkPath -> $targetPath"
}

function Write-Launchers([string]$rootDir, [int]$listenPort) {
    $start247 = @"
@echo off
cd /d "%~dp0"
if "%PORT%"=="" set PORT=$listenPort
set PYT=%~dp003_voice_clone\venv\Scripts\python.exe
if not exist "%PYT%" (
    echo [ERROR] Khong tim thay 03_voice_clone\venv\Scripts\python.exe. Hay chay install.bat truoc!
    pause
    exit /b 1
)
:loop
echo [%date% %time%] Dang khoi dong TikTok Studio 24/7 tai http://0.0.0.0:%PORT% ...
"%PYT%" -m uvicorn scripts.webapp.app:app --host 0.0.0.0 --port %PORT%
echo [%date% %time%] Server da dung. Tu dong khoi dong lai sau 3 giay...
timeout /t 3 /nobreak >nul
goto loop
"@
    [IO.File]::WriteAllText((Join-Path $rootDir "start_server_24_7.bat"), $start247, [Text.Encoding]::ASCII)

    $startLocal = @"
@echo off
cd /d "%~dp0"
if "%PORT%"=="" set PORT=$listenPort
set PYT=%~dp003_voice_clone\venv\Scripts\python.exe
if not exist "%PYT%" (
    echo [ERROR] Khong tim thay venv. Hay chay install.bat truoc!
    pause
    exit /b 1
)
start "" "http://127.0.0.1:%PORT%"
"%PYT%" -m uvicorn scripts.webapp.app:app --host 0.0.0.0 --port %PORT%
"@
    [IO.File]::WriteAllText((Join-Path $rootDir "start_studio.bat"), $startLocal, [Text.Encoding]::ASCII)
    Write-Ok "Da tao start_studio.bat & start_server_24_7.bat (Port: $listenPort)"
}

function Ensure-ChannelDirs([string]$rootDir, [switch]$IncludeModelDir) {
    $dirs = @("projects", "01_video_mau", "02_video_tho", "04_workspace", "remotion_studio\public\workspace")
    if ($IncludeModelDir) { $dirs += "03_voice_clone\model" }
    foreach ($sub in $dirs) {
        Ensure-Directory (Join-Path $rootDir $sub)
    }
}

# ==============================================================================
# MODE B: CLONE MULTI-CHANNEL (Zero-Disk Windows Junctions + Isolated Workspace)
# ==============================================================================
if ($CloneTo -ne "") {
    $Dest = [IO.Path]::GetFullPath($CloneTo)
    Write-Info "Nhan ban kenh doc lap sang: $Dest (Port $Port)..."
    Ensure-Directory $Dest
    Ensure-ChannelDirs $Dest

    # Copy lightweight code & configs
    foreach ($dirRel in @("scripts", ".agents", "remotion_studio\src")) {
        $s = Join-Path $SourceRoot $dirRel
        if (Test-Path -LiteralPath $s) {
            Ensure-Directory (Join-Path $Dest $dirRel)
            robocopy $s (Join-Path $Dest $dirRel) /E /XD __pycache__ .pytest_cache | Out-Null
        }
    }
    foreach ($fileRel in @(
        "requirements.txt", "install.bat", "update.bat", "clone_new_channel.bat", "pack_portable.ps1", ".gitignore", "README.md",
        "remotion_studio\package.json", "remotion_studio\package-lock.json", "remotion_studio\tsconfig.json", "remotion_studio\remotion.config.ts",
        "hyperframes_studio\package.json", "hyperframes_studio\package-lock.json"
    )) {
        $s = Join-Path $SourceRoot $fileRel
        if (Test-Path -LiteralPath $s) {
            $d = Join-Path $Dest $fileRel
            Ensure-Directory (Split-Path -Parent $d)
            Copy-Item -LiteralPath $s -Destination $d -Force
        }
    }

    # Copy customizable default voice clone templates
    foreach ($vcSub in @("voices")) {
        $vs = Join-Path $SourceRoot "03_voice_clone\$vcSub"
        if (Test-Path -LiteralPath $vs) {
            robocopy $vs (Join-Path $Dest "03_voice_clone\$vcSub") /E | Out-Null
        }
    }
    foreach ($vcFile in @("giong_mau.wav", "noi_dung_giong_mau.txt")) {
        $vf = Join-Path $SourceRoot "03_voice_clone\$vcFile"
        if (Test-Path -LiteralPath $vf) {
            Copy-Item -LiteralPath $vf -Destination (Join-Path $Dest "03_voice_clone\$vcFile") -Force
        }
    }

    # Link heavy shared read-only directories via Windows Junction (0 MB extra disk)
    Ensure-Junction (Join-Path $Dest "03_voice_clone\venv") (Join-Path $SourceRoot "03_voice_clone\venv")
    Ensure-Junction (Join-Path $Dest "03_voice_clone\model") (Join-Path $SourceRoot "03_voice_clone\model")
    Ensure-Junction (Join-Path $Dest "03_voice_clone\piper_voices") (Join-Path $SourceRoot "03_voice_clone\piper_voices")
    Ensure-Junction (Join-Path $Dest "assets") (Join-Path $SourceRoot "assets")
    Ensure-Junction (Join-Path $Dest "06_assets_audio") (Join-Path $SourceRoot "06_assets_audio")
    Ensure-Junction (Join-Path $Dest "remotion_studio\node_modules") (Join-Path $SourceRoot "remotion_studio\node_modules")
    Ensure-Junction (Join-Path $Dest "remotion_studio\public\assets") (Join-Path $SourceRoot "remotion_studio\public\assets")
    Ensure-Junction (Join-Path $Dest "hyperframes_studio\node_modules") (Join-Path $SourceRoot "hyperframes_studio\node_modules")

    Write-Launchers $Dest $Port
    Write-Host ""
    Write-Ok "HOAN TAT NHAN BAN KENH MOI tai: $Dest"
    Write-Info "Khi chay start_studio.bat tai $Dest (cong $Port), giao dien se tu dong hoi Ten Kenh lan dau!"
    exit 0
}

# ==============================================================================
# MODE A: STANDARD INSTALL / PATH-SAFE REPAIR IN TARGET DIRECTORY
# ==============================================================================
$Root = if ($TargetDir -ne "") { [IO.Path]::GetFullPath($TargetDir) } else { $SourceRoot }
if ($Root -ne $SourceRoot) {
    Write-Info "Sao chep du an sang thu muc chi dinh: $Root ..."
    Ensure-Directory $Root
    robocopy $SourceRoot $Root /E /XD projects 04_workspace 01_video_mau 02_video_tho venv node_modules __pycache__ .git .remotion /XF *.zip channel_profile.json | Out-Null
}
Ensure-ChannelDirs $Root -IncludeModelDir

# 1. Check Base System Tools (Python, Node, FFmpeg)
$sysPy = Get-Command python -ErrorAction SilentlyContinue
if (-not $sysPy) {
    throw "Chua tim thay Python tren may! Hay cai Python 3.10-3.12 (hoac winget install Python.Python.3.11) roi chay lai."
}
$npmCmd = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npmCmd) {
    Write-Info "Chua thay Node.js/npm. Thu cai qua winget..."
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
}
$ffCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffCmd) {
    Write-Info "Chua thay FFmpeg. Thu cai qua winget..."
    winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
}

# 2. Validate or Rebuild 03_voice_clone\venv for exact TargetDir path
$VenvDir = Join-Path $Root "03_voice_clone\venv"
$VenvPy = Join-Path $VenvDir "Scripts\python.exe"
$PyVenvCfg = Join-Path $VenvDir "pyvenv.cfg"
$NeedVenvBuild = $ForceVenv -or (-not (Test-Path -LiteralPath $VenvPy))

if (-not $NeedVenvBuild) {
    try {
        $probeOut = & $VenvPy -c "import sys, fastapi, uvicorn; print(sys.prefix)" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $probeOut) { $NeedVenvBuild = $true }
    } catch {
        $NeedVenvBuild = $true
    }
}

if ($NeedVenvBuild) {
    Write-Info "Tao moi moi truong ao Python tai: $VenvDir ..."
    if (Test-Path -LiteralPath $VenvDir) { Remove-Item -LiteralPath $VenvDir -Recurse -Force }
    & $sysPy.Source -m venv $VenvDir
    & $VenvPy -m pip install --upgrade pip
    $hasGpu = $null -ne (Get-Command nvidia-smi -ErrorAction SilentlyContinue)
    if ($hasGpu) {
        Write-Info "Phat hien NVIDIA GPU -> cai PyTorch CUDA..."
        & $VenvPy -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
    } else {
        Write-Info "Cai PyTorch CPU..."
        & $VenvPy -m pip install torch torchaudio
    }
    $reqFile = Join-Path $Root "requirements.txt"
    if (Test-Path -LiteralPath $reqFile) {
        & $VenvPy -m pip install -r $reqFile
    }
    Write-Ok "Da cai xong moi truong Python tai $VenvDir"
} else {
    Write-Ok "Python venv hop le tai $VenvDir"
}

# 3. Check & Auto-Download F5-TTS-Vietnamese model_last.pt if missing
$ModelPt = Join-Path $Root "03_voice_clone\model\model_last.pt"
$ModelVocab = Join-Path $Root "03_voice_clone\model\vocab.txt"
$needModel = (-not (Test-Path -LiteralPath $ModelPt)) -or ((Get-Item -LiteralPath $ModelPt).Length -lt 100MB)
if ($needModel) {
    Write-Info "Dang tai F5-TTS Vietnamese model (model_last.pt ~640MB)..."
    try {
        $hfUrl = "https://huggingface.co/hynt/F5-TTS-Vietnamese-ViVoice/resolve/main/model_last.pt"
        Invoke-WebRequest -Uri $hfUrl -OutFile $ModelPt -UseBasicParsing
        Write-Ok "Da tai xong model_last.pt!"
    } catch {
        Write-Warning "Khong the tu tai model_last.pt ($($_.Exception.Message)). Hay copy file model_last.pt vao $ModelPt thu cong."
    }
} else {
    Write-Ok "Model F5-TTS da san sang: $ModelPt"
}
if (-not (Test-Path -LiteralPath $ModelVocab)) {
    try {
        Invoke-WebRequest -Uri "https://huggingface.co/hynt/F5-TTS-Vietnamese-ViVoice/resolve/main/vocab.txt" -OutFile $ModelVocab -UseBasicParsing
    } catch {}
}

# 3b. Check & Auto-Download Piper Vietnamese Offline Voices if missing
$PiperDir = Join-Path $Root "03_voice_clone\piper_voices"
New-Item -ItemType Directory -Path $PiperDir -Force | Out-Null
$piperBase = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
$piperModels = @(
    @{ Name = "vi_VN-vais1000-medium.onnx"; Rel = "vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx" },
    @{ Name = "vi_VN-25hours_single-low.onnx"; Rel = "vi/vi_VN/25hours_single/low/vi_VN-25hours_single-low.onnx" },
    @{ Name = "vi_VN-vivos-x_low.onnx"; Rel = "vi/vi_VN/vivos/x_low/vi_VN-vivos-x_low.onnx" }
)
foreach ($pm in $piperModels) {
    $onnxDest = Join-Path $PiperDir $pm.Name
    $jsonDest = Join-Path $PiperDir ($pm.Name + ".json")
    if (-not (Test-Path -LiteralPath $onnxDest)) {
        Write-Info "Dang tai Piper Voice offline: $($pm.Name)..."
        try {
            Invoke-WebRequest -Uri ($piperBase + $pm.Rel) -OutFile $onnxDest -UseBasicParsing
        } catch {
            Write-Warning "Khong the tai $($pm.Name): $($_.Exception.Message)"
        }
    }
    if (-not (Test-Path -LiteralPath $jsonDest)) {
        try {
            Invoke-WebRequest -Uri ($piperBase + $pm.Rel + ".json") -OutFile $jsonDest -UseBasicParsing
        } catch {}
    }
}

# 4. Install Node dependencies for Remotion & HyperFrames
foreach ($nodeProj in @("remotion_studio", "hyperframes_studio")) {
    $npDir = Join-Path $Root $nodeProj
    $pkgJson = Join-Path $npDir "package.json"
    $nmDir = Join-Path $npDir "node_modules"
    if ((Test-Path -LiteralPath $pkgJson) -and (-not (Test-Path -LiteralPath $nmDir))) {
        Write-Info "Dang chay npm install trong $nodeProj..."
        Push-Location $npDir
        npm install --no-audit --no-fund
        Pop-Location
        Write-Ok "Da cai xong node_modules cho $nodeProj"
    }
}

# 5. Ensure Fonts, SFX, BGM & Sync to Remotion Public
Write-Info "Dong bo tai nguyen (Fonts, SFX, BGM, Stickers, Overlays)..."
Push-Location $Root
try {
    & $VenvPy "scripts\setup_assets.py" | Out-Null
    & $VenvPy "scripts\generate_audio_assets.py" | Out-Null
    & $VenvPy "scripts\audio_bgm.py" | Out-Null
    & $VenvPy -c "import sys; sys.path.insert(0,'scripts'); import remotion_renderer; remotion_renderer.sync_media_to_remotion_public()" | Out-Null
} catch {
    Write-Warning "Luu y dong bo tai nguyen: $($_.Exception.Message)"
}
Pop-Location

Write-Launchers $Root $Port
Write-Host ""
Write-Ok "CAI DAT HOAN TAT tai: $Root (Cong mac dinh: $Port)"
Write-Info "Chay start_studio.bat de su dung ngay, hoac start_server_24_7.bat tren may chu 24/7!"
