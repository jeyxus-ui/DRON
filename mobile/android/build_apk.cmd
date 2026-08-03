@echo off
set ANDROID_HOME=C:\Users\Julian\Android\Sdk
call gradlew.bat assembleRelease
echo Exit code: %ERRORLEVEL%
