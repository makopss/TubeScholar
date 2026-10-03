@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ================================================================
echo  🎓 TubeScholar Windows 설치 프로그램 자동 빌드 스크립트
echo ================================================================
echo.

cd /d "%~dp0"

:: 1. 가상환경 및 PyInstaller 확인
if not exist ".venv\Scripts\pyinstaller.exe" (
    echo [*] PyInstaller가 설치되어 있지 않습니다. 가상환경에 설치합니다...
    .venv\Scripts\pip install pyinstaller
    if errorlevel 1 (
        echo [!] PyInstaller 설치 실패. 네트워크 상태나 가상환경을 확인해주세요.
        pause
        exit /b 1
    )
)

:: 2. 기존 빌드 폴더 정리
echo [*] 이전 빌드 캐시를 정리하는 중...
if exist "build" rmdir /s /q "build"
if exist "dist\TubeScholar" rmdir /s /q "dist\TubeScholar"

:: 3. PyInstaller 패키징 실행
echo [*] TubeScholar 독립 실행 파일 빌드 중 (PyInstaller onedir 모드)...
.venv\Scripts\pyinstaller.exe --noconfirm --clean TubeScholar.spec
if errorlevel 1 (
    echo.
    echo [!] PyInstaller 빌드 중 오류가 발생했습니다.
    pause
    exit /b 1
)
echo [*] PyInstaller 바이너리 빌드 완료!

:: 4. Inno Setup 컴파일러(ISCC.exe) 찾기
set "ISCC_PATH="
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
) else if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe"
) else (
    where iscc.exe >nul 2>nul
    if not errorlevel 1 (
        set "ISCC_PATH=iscc.exe"
    )
)

if "%ISCC_PATH%"=="" (
    echo.
    echo [!] Inno Setup 6 컴파일러(ISCC.exe)를 찾을 수 없습니다.
    echo [*] Inno Setup 6을 설치해주세요: winget install JRSoftware.InnoSetup
    pause
    exit /b 1
)

:: 5. Inno Setup으로 설치 파일(Setup.exe) 생성
echo.
echo [*] Inno Setup 컴파일러 실행 중 (%ISCC_PATH%)...
"%ISCC_PATH%" installer.iss
if errorlevel 1 (
    echo.
    echo [!] Inno Setup 컴파일 실패.
    pause
    exit /b 1
)

echo.
echo ================================================================
echo  ✨ TubeScholar Windows 설치 파일이 성공적으로 제작되었습니다!
echo ================================================================
echo.
echo  📍 설치 파일 위치:
echo     dist\installer\TubeScholar-Setup-v1.0.0.exe
echo.
echo  이제 위 Setup 파일을 다른 PC로 전달하여 설치 마법사로 설치할 수 있습니다.
echo ================================================================
echo.
pause
