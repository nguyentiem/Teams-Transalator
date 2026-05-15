@echo off
REM ============================================================
REM  Build script: Teams Translator -> .exe
REM  Chạy file này trong thư mục chứa main.py
REM ============================================================

echo [1/4] Kiem tra Python...
python --version
if errorlevel 1 (
    echo ❌ Python chưa cài. Tải tại https://python.org
    pause & exit /b 1
)

echo.
echo [2/4] Cai dat thu vien...
pip install soundcard SpeechRecognition googletrans==4.0.0rc1 numpy pyaudio pyinstaller
if errorlevel 1 (
    echo ❌ Lỗi cài đặt thư viện.
    pause & exit /b 1
)

echo.
echo [3/4] Build .exe bang PyInstaller...
pyinstaller ^
  --onefile ^
  --windowed ^
  --name "TeamsTranslator" ^
  --add-data "README.md;." ^
  --hidden-import=speech_recognition ^
  --hidden-import=soundcard ^
  --hidden-import=googletrans ^
  --hidden-import=googletrans.adapters ^
  --hidden-import=httpx ^
  main.py

if errorlevel 1 (
    echo ❌ Build thất bại. Xem log ở trên.
    pause & exit /b 1
)

echo.
echo [4/4] ✅ Build thành công!
echo File .exe nằm trong thư mục: dist\TeamsTranslator.exe
echo.
pause
