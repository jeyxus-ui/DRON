#!/bin/bash

# Script de despliegue para Raspberry Pi con Pixhawk

echo "Actualizando sistema..."
sudo apt update && sudo apt upgrade -y

echo "Instalando dependencias..."
sudo apt install -y git curl

echo "Instalando Docker..."
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

echo "Reinicia la sesión o ejecuta 'newgrp docker' para aplicar cambios de grupo."

echo "Clonando proyecto..."
git clone <tu-repo-url> back-mavlink
cd back-mavlink

echo "Construyendo e iniciando servicios..."
docker-compose up --build -d

echo "Despliegue completado. Accede a http://<IP_Raspberry>:3000"