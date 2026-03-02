@echo off
cd /d C:\Users\georg\Arbeitszeit_gpt
echo Django Server wird gestartet...
echo Dieses Fenster OFFEN lassen!
echo Server laeuft auf http://127.0.0.1:8000/
echo.
call env\Scripts\activate.bat
python manage.py runserver
pause
