@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title bookmark manager launcher

rem всегда переходим в папку где лежит cmd
cd /d "%~dp0"

:menu
cls
echo ==============================
echo   bookmark manager launcher
echo ==============================
echo текущая папка: %cd%
echo.
echo 1 - запустить приложение
echo 2 - создать/пересоздать venv
echo 3 - установить зависимости (requirements.txt)
echo 4 - создать/обновить .env
echo 5 - открыть сайт в браузере
echo 6 - показать адрес сайта
echo 7 - выйти
echo.
set /p choice=выбери вариант (1-7): 

if "%choice%"=="1" goto run_app
if "%choice%"=="2" goto create_venv
if "%choice%"=="3" goto install_deps
if "%choice%"=="4" goto make_env
if "%choice%"=="5" goto open_site
if "%choice%"=="6" goto show_url
if "%choice%"=="7" goto end

echo.
echo неправильный выбор
pause
goto menu


:run_app
cls
cd /d "%~dp0"

if not exist "app.py" (
  echo не найден app.py в папке: %cd%
  echo проверь, что run.cmd лежит рядом с app.py
  pause
  goto menu
)

if exist ".venv\Scripts\python.exe" (
  echo найдено .venv, запускаю через неё
  set PYEXE=.venv\Scripts\python.exe
) else (
  echo .venv не найдена, сначала сделай пункт 2
  pause
  goto menu
)

echo.
echo запускаем приложение...
echo ссылка: http://127.0.0.1:5000/links
echo база: %cd%\instance\bookmarks.db
echo чтобы остановить сервер: нажми ctrl+c в этом окне
echo.

start "" "http://127.0.0.1:5000/links"

"%PYEXE%" app.py

echo.
echo сервер остановлен
pause
goto menu


:create_venv
cls
cd /d "%~dp0"

if not exist "app.py" (
  echo не найден app.py в папке: %cd%
  echo проверь, что run.cmd лежит рядом с app.py
  pause
  goto menu
)

echo создаём/пересоздаём venv...
if exist ".venv" (
  echo папка .venv уже есть. удалить и создать заново?
  set /p delv=введи y чтобы удалить, иначе n: 
  if /i "!delv!"=="y" (
    rmdir /s /q ".venv"
  ) else (
    echo пропускаю пересоздание venv
    pause
    goto menu
  )
)

python -m venv .venv

echo.
echo venv готова
pause
goto menu


:install_deps
cls
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo venv не найдена. сначала сделай пункт 2
  pause
  goto menu
)

if not exist "requirements.txt" (
  echo не найден requirements.txt рядом с app.py
  echo создай requirements.txt и добавь туда зависимости
  pause
  goto menu
)

echo обновляем pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip

echo ставим зависимости из requirements.txt...
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo готово
pause
goto menu


:make_env
cls
cd /d "%~dp0"

if exist ".env" (
  echo файл .env уже существует
  echo если хочешь перезаписать, введи y
  set /p overw=перезаписать? (y/n): 
  if /i not "!overw!"=="y" (
    echo оставляю текущий .env
    pause
    goto menu
  )
)

echo создаю .env...

rem простая генерация "рандома" из даты/времени (не крипто, но для локалки норм)
set KEY=dev_%random%%random%%random%%random%%random%

(
  echo SECRET_KEY=!KEY!
  echo FLASK_DEBUG=1
) > .env

echo.
echo .env создан
echo SECRET_KEY установлен
pause
goto menu


:open_site
start "" "http://127.0.0.1:5000/links"
echo сайт открыт (если сервер запущен)
pause
goto menu


:show_url
echo.
echo адрес сайта: http://127.0.0.1:5000/links
echo база: %cd%\instance\bookmarks.db
echo если не открывается, сначала запусти сервер (пункт 1)
pause
goto menu


:end
echo пока
pause
exit /b