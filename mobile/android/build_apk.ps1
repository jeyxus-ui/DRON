$env:ANDROID_HOME = "C:\Users\Julian\Android\Sdk"
Set-Location "C:\Users\Julian\Desktop\hh\Dron\mobile\android"
& .\gradlew.bat assembleRelease
Write-Host "EXIT: $LASTEXITCODE"
