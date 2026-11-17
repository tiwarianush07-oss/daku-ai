@echo off
setlocal

rem Check if py launcher is available, otherwise fallback to python
where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set PY_CMD=py
) else (
    set PY_CMD=python
)

if "%~1"=="doctor" goto do_doctor
if "%~1"=="client" goto do_client
if "%~1"=="server" goto do_server
if "%~1"=="hud" goto do_hud
if "%~1"=="test" goto do_test

%PY_CMD% "%~dp0main.py" %*
goto :eof

:do_doctor
shift
%PY_CMD% "%~dp0doctor.py" %1 %2 %3 %4 %5 %6 %7 %8 %9
goto :eof

:do_client
shift
%PY_CMD% "%~dp0client.py" %1 %2 %3 %4 %5 %6 %7 %8 %9
goto :eof

:do_server
shift
%PY_CMD% "%~dp0server\daku_server.py" %1 %2 %3 %4 %5 %6 %7 %8 %9
goto :eof

:do_hud
shift
%PY_CMD% "%~dp0server\daku_server.py" --hud %1 %2 %3 %4 %5 %6 %7 %8 %9
goto :eof

:do_test
shift
%PY_CMD% -m unittest discover -s "%~dp0tests" -v %1 %2 %3 %4 %5 %6 %7 %8 %9
goto :eof
