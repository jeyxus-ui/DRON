@echo off
set ANDROID_HOME=C:\Users\USUARIO\AppData\Local\Android\Sdk
call gradlew.bat assembleRelease
echo Exit code: %ERRORLEVEL%
