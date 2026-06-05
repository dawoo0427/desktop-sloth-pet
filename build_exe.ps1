# 나무늘보 데스크탑 펫 -> 단일 exe 빌드 (Windows)
# 사용법: PowerShell에서  ./build_exe.ps1   실행 (또는 우클릭 > PowerShell로 실행)
# 결과물: dist\DesktopSlothPet.exe  (이 파일 하나만 배포하면 됨, 파이썬 불필요)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# 1) PyInstaller 설치 확인
python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller 설치 중..." -ForegroundColor Cyan
    python -m pip install --user pyinstaller
}

# 2) 빌드 (frames 폴더를 exe 안에 포함, 콘솔창 없음, 아이콘 적용)
Write-Host "빌드 중... (몇 분 걸릴 수 있어요)" -ForegroundColor Cyan
python -m PyInstaller --onefile --noconsole --clean `
    --name "DesktopSlothPet" `
    --icon "pet.ico" `
    --add-data "frames;frames" `
    pet.py

Write-Host ""
Write-Host "완료! ->  $PSScriptRoot\dist\DesktopSlothPet.exe" -ForegroundColor Green
Write-Host "이 exe 파일 하나만 친구에게 보내면 됩니다 (Windows, 더블클릭 실행)." -ForegroundColor Green
