$env:ANDROID_HOME = "C:\Users\USUARIO\AppData\Local\Android\Sdk"
Set-Location "C:\Users\USUARIO\Desktop\Drones\dron r\Dron\mobile\android"
& .\gradlew.bat assembleRelease
Write-Host "EXIT: $LASTEXITCODE"
