@echo off
cd /d "%~dp0"

echo Verification de l'environnement virtuel...
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate
    goto LUNCH
) 
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate
    goto LUNCH
)

:: Si aucun des deux n'est trouve, cherchons le nom du dossier d'env virtuel present
for /d %%D in (*) do (
    if exist "%%D\Scripts\activate.bat" (
        echo Environnement trouve dans : %%D
        call "%%D\Scripts\activate.bat"
        goto LUNCH
    )
)

echo.
echo [ERREUR CRITIQUE] Aucun environnement virtuel Python n'a ete detecte dans ce dossier !
pause
exit /b

:LUNCH
echo.
echo Environnement virtuel active avec succes.
echo Lancement de app.py...
python app.py
pause