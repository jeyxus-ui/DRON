"""
Actualiza los .docx en documentacion/ con contenido profesional universitario.
Genera desde análisis completo del código real del proyecto.
"""
import os, sys, io, tempfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Emu
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.text import WD_ALIGN_PARAGRAPH

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(RAIZ, 'documentacion')
os.makedirs(OUT_DIR, exist_ok=True)
AZUL = RGBColor(0x00, 0x55, 0x88)
GRIS = RGBColor(0x66, 0x66, 0x66)
VERDE = RGBColor(0x00, 0x80, 0x00)
ROJO = RGBColor(0xCC, 0x00, 0x00)

def add_run(p, text, bold=False, italic=False, color=None, size=None):
    r = p.add_run(text)
    if bold: r.bold = True
    if italic: r.italic = True
    if color: r.font.color.rgb = color
    if size: r.font.size = Pt(size)
    return r

def add_h(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    for r in h.runs:
        r.font.color.rgb = AZUL
    return h

def add_b(doc, text, bold_prefix=None):
    p = doc.add_paragraph(style='List Bullet')
    if bold_prefix:
        add_run(p, bold_prefix, bold=True)
        add_run(p, text)
    else:
        add_run(p, text)

def add_code_block(doc, txt):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.left_indent = Inches(0.3)
    run = p.add_run(txt)
    run.font.name = 'Consolas'
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    shading = OxmlElement('w:shd')
    shading.set(qn('w:fill'), 'F0F0F0')
    shading.set(qn('w:val'), 'clear')
    p.paragraph_format.element.get_or_add_pPr().append(shading)

def add_tbl(doc, headers, rows):
    t = doc.add_table(rows=len(rows)+1, cols=len(headers))
    t.style = 'Light Grid Accent 1'
    t.alignment = 1
    for i, h in enumerate(headers):
        r = t.cell(0, i).paragraphs[0].add_run(h)
        r.bold = True; r.font.size = Pt(9)
    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row):
            t.cell(ri+1, ci).text = ''
            r = t.cell(ri+1, ci).paragraphs[0].add_run(str(cell))
            r.font.size = Pt(9)
    doc.add_paragraph()

def add_tbl_bordered(doc, headers, rows, col_widths=None):
    t = doc.add_table(rows=len(rows)+1, cols=len(headers))
    t.style = 'Light Grid Accent 1'
    t.alignment = 1
    for i, h in enumerate(headers):
        r = t.cell(0, i).paragraphs[0].add_run(h)
        r.bold = True; r.font.size = Pt(9)
    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row):
            t.cell(ri+1, ci).text = ''
            r = t.cell(ri+1, ci).paragraphs[0].add_run(str(cell))
            r.font.size = Pt(9)
    doc.add_paragraph()
    return t

def cfg(doc):
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(11)
    style.paragraph_format.space_after = Pt(6)
    for s in doc.sections:
        s.top_margin = Inches(0.8)
        s.bottom_margin = Inches(0.8)
        s.left_margin = Inches(0.9)
        s.right_margin = Inches(0.9)

def add_sep(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)

# ── MANUAL USUARIO ────────────────────────────────────────────
def gen_usuario():
    doc = Document(); cfg(doc)

    # Portada
    add_h(doc, 'Manual de Usuario', 0)
    add_h(doc, 'Sistema de Control y Telemetria para Drones', 1)
    p = doc.add_paragraph()
    add_run(p, 'Version 1.0.0  |  Mayo 2026', italic=True, color=GRIS)
    p2 = doc.add_paragraph()
    add_run(p2, 'Documentacion tecnico-operativa del sistema de control drone ', italic=True, color=GRIS)
    add_run(p2, 'con sensores MTF01, YDLIDAR X4PRO, camara RealSense D435i', italic=True, color=GRIS)
    add_run(p2, 'y navegacion autonoma con evitacion de obstaculos', italic=True, color=GRIS)
    doc.add_paragraph()

    # 1
    add_h(doc, '1. Introduccion al Sistema', 2)
    doc.add_paragraph(
        'El Sistema de Control y Telemetria para Drones es una plataforma integral que permite '
        'operar un vehiculo aereo no tripulado (UAV) compatible con ArduPilot/PX4 desde un dispositivo '
        'movil Android. El sistema se compone de tres elementos principales:'
    )
    add_b(doc, 'Servidor embebido (Raspberry Pi 4)', bold_prefix='Backend: ')
    doc.add_paragraph(
        'Ejecuta el servidor FastAPI en Python que se conecta al controlador de vuelo (Pixhawk) via '
        'MAVLink por USB. Procesa los datos de los sensores MTF01 (ultrasonico), YDLIDAR X4PRO (laser 360°) '
        'y camara RealSense D435i, y ejecuta la logica de navegacion autonoma con evitacion de obstaculos.'
    )
    add_b(doc, 'Aplicacion movil Android (React Native)', bold_prefix='Frontend: ')
    doc.add_paragraph(
        'Interfaz de usuario que se conecta al servidor via WiFi local. Proporciona telemetria en '
        'tiempo real, control manual (joysticks virtuales), comandos de mision, visualizacion de '
        'mapa GPS, camara en vivo y monitoreo de sensores.'
    )
    add_b(doc, 'Protocolo MAVLink', bold_prefix='Comunicacion: ')
    doc.add_paragraph(
        'Protocolo estandar de la industria para comunicacion con autopilotos. El backend se conecta '
        'al Pixhawk via USB (115200 baud) y traduce los comandos del usuario a mensajes MAVLink.'
    )

    add_h(doc, '1.1 Arquitectura general', 2)
    add_code_block(doc,
        '+------------------+         WiFi          +-------------------+\n'
        '|  App Android     | <-------------------->|  Backend FastAPI  |\n'
        '|  React Native    |   REST + WebSocket    |  Python 3.12      |\n'
        '+------------------+                       |  RPi4 / Laptop    |\n'
        '                                           |                   |\n'
        '                                           |  +-------------+  |\n'
        '                                           |  | MAVLink     |<-|---- USB ---> Pixhawk\n'
        '                                           |  | Controller  |  |\n'
        '                                           |  +-------------+  |\n'
        '                                           |  | Sensores    |  |\n'
        '                                           |  | - MTF01 I2C |  |\n'
        '                                           |  | - YDLIDAR   |  |\n'
        '                                           |  |   USB/serial|  |\n'
        '                                           |  | - Camara    |  |\n'
        '                                           |  |   USB       |  |\n'
        '                                           |  +-------------+  |\n'
        '                                           |  | Navigation  |  |\n'
        '                                           |  | Controller  |  |\n'
        '                                           |  +-------------+  |\n'
        '+------------------+                       +-------------------+'
    )

    add_h(doc, '1.2 Hardware requerido', 2)
    add_tbl(doc, ['Componente', 'Especificacion', 'Conexion'], [
        ['Raspberry Pi 4', '4GB RAM, Raspberry Pi OS', 'Ejecuta el backend'],
        ['Pixhawk (PX4/ArduPilot)', 'Cualquier version compatible', 'USB al backend'],
        ['MTF01', 'Ultrasonico 2cm-4m, I2C addr 0x57', 'I2C (SDA/SCL) a RPi4'],
        ['YDLIDAR X4PRO', 'Laser 360°, 0.12m-10m, 720pts', 'USB/serial 115200 baud'],
        ['Camara (opcional)', 'RealSense D435i o webcam USB', 'USB a RPi4'],
        ['Telefono Android', 'Android 8+, 2GB RAM', 'WiFi al backend'],
    ])

    # 2
    add_h(doc, '2. Conexion y configuracion inicial', 2)
    add_h(doc, '2.1 Conexion del hardware', 3)
    doc.add_paragraph(
        '1. Conecte el Pixhawk al puerto USB de la RPi4 (aparece como /dev/ttyACM0)\n'
        '2. Conecte el MTF01 a los pines I2C de la RPi4:\n'
        '   - VCC (rojo) -> pin 1 (3.3V)\n'
        '   - GND (negro) -> pin 6 (GND)\n'
        '   - SCL (amarillo) -> pin 5 (GPIO 3/SCL)\n'
        '   - SDA (verde) -> pin 3 (GPIO 2/SDA)\n'
        '3. Conecte el YDLIDAR X4PRO via adaptador USB (aparece como /dev/ttyUSB0)\n'
        '4. Conecte la camara RealSense o webcam USB\n'
        '5. Asegure que el telefono Android este en la misma red WiFi que la RPi4'
    )
    
    add_h(doc, '2.2 Encendido del servidor', 3)
    doc.add_paragraph(
        'El servidor detecta automaticamente los dispositivos conectados. Si no encuentra '
        'hardware real, entra en modo SIM (simulacion) con datos sinteticos realistas.\n\n'
        'Pasos para iniciar:'
    )
    add_code_block(doc,
        '# Clonar el repositorio\n'
        'git clone <repo> back-mavlink\n'
        'cd back-mavlink\n'
        '\n'
        '# Instalar dependencias\n'
        'pip install -r backend/requirements.txt\n'
        '\n'
        '# Forzar modo simulacion (opcional)\n'
        'export MAVLINK_DEVICE=SIM\n'
        '\n'
        '# Iniciar servidor\n'
        'uvicorn backend.main:app --host 0.0.0.0 --port 8000'
    )
    doc.add_paragraph(
        'Al arrancar, el servidor muestra en consola que dispositivos detecto:\n'
        '- "Modo simulador activado" -> sin hardware, datos simulados\n'
        '- "MAVLink controller initialized: device=..." -> conexion establecida\n'
        '- "SensorManager iniciado" -> sensores listos\n'
        '- "NavigationController iniciado" -> navegacion autonoma activa'
    )

    add_h(doc, '2.3 Conexion de la app movil', 3)
    doc.add_paragraph(
        '1. Instale el APK en su telefono Android\n'
        '2. Configure la IP del servidor en la app (Menu -> Configuracion -> IP del servidor)\n'
        '   Use la IP local de la RPi4 (ej: 192.168.1.100)\n'
        '3. La app se conectara automaticamente via WebSocket\n'
        '4. Si no hay servidor disponible, la app entra en modo DEMO local\n'
        '   con datos simulados de telemetria'
    )

    # 3
    add_h(doc, '3. Interfaz de la aplicacion', 2)
    add_h(doc, '3.1 Pantalla principal (CONTROL)', 3)
    doc.add_paragraph(
        'La pantalla principal se organiza en varias zonas:\n\n'
        'Zona superior:\n'
        '- Indicador de conexion (verde/rojo)\n'
        '- Modo de vuelo actual (STABILIZE, GUIDED, AUTO, etc.)\n'
        '- Indicador de ARM/DISARM\n'
        '- Modo DEMO (si aplica)\n\n'
        'Zona central - Video:\n'
        '- Transmision de la camara en vivo (si esta conectada)\n'
        '- HUD con datos de vuelo superpuestos\n'
        '- Detecciones de objetos (YOLOv8) con cuadros delimitadores\n\n'
        'Zona de joysticks:\n'
        '- Joystick izquierdo: control de throttle y yaw\n'
        '  (Modo 2: el throttle se mantiene al soltar)\n'
        '- Joystick derecho: control de pitch y roll\n\n'
        'Botones tacticos:\n'
        '- ARM/DISARM: armar/desarmar motores\n'
        '- TAKEOFF: despegue autonomo (altitud configurable)\n'
        '- LAND: aterrizaje\n'
        '- SOS/RTL: retorno a casa de emergencia\n\n'
        'Panel lateral:\n'
        '- Selector de modos de vuelo (16 modos disponibles)\n'
        '- Indicador de bateria con porcentaje\n'
        '- Estado de sensores (iconos verdes si activos)\n'
        '- Acceso a comandos de navegacion'
    )

    add_h(doc, '3.2 Pantalla de telemetria (DATA)', 3)
    doc.add_paragraph(
        'Muestra en tiempo real todos los datos del dron:\n\n'
        'Estado general:\n'
        '- Modo de vuelo, estado ARM/DISARM\n'
        '- Horizonte artificial (indicador de actitud)\n\n'
        'Velocidad:\n'
        '- Velocidad horizontal (m/s) con barra de progreso\n'
        '- Velocidad vertical (m/s) con barra de progreso\n\n'
        'Posicion y GPS:\n'
        '- Altitud (m)\n'
        '- Latitud / Longitud\n'
        '- Satelites visibles\n'
        '- HDOP (precision horizontal)\n\n'
        'Bateria:\n'
        '- Voltaje (V)\n'
        '- Porcentaje restante con barra de colores\n'
        '- Corriente (A)\n\n'
        'Sensores (nuevo):\n'
        '- Distancia ultrasonido MTF01 (m)\n'
        '- Obstaculo laser mas cercano (distancia y angulo)\n'
        '- Puntos del escaneo YDLIDAR\n'
        '- Alarma de obstaculo al frente'
    )

    add_h(doc, '3.3 Pantalla de mapa (GPS)', 3)
    doc.add_paragraph(
        '- Mapa interactivo con la posicion actual del dron\n'
        '- Animacion de pulso en la posicion del dron\n'
        '- Circulo de precision GPS\n'
        '- Waypoints visualizados en el mapa\n'
        '- Ruta de mision dibujada como polilinea\n'
        '- Toque en el mapa para anadir waypoints (selector de altitud)\n'
        '- Panel inferior con coordenadas y lista de waypoints'
    )

    add_h(doc, '3.4 Pantalla de waypoints (ROUTE)', 3)
    doc.add_paragraph(
        '- Entrada de waypoints relativos (forward, right, up)\n'
        '- Lista de waypoints con botones goto/eliminar\n'
        '- Guardar/cargar conjuntos de waypoints en el servidor\n'
        '- Acciones de mision: subir, iniciar, limpiar'
    )

    # 4
    add_h(doc, '4. Sensores de distancia', 2)
    add_h(doc, '4.1 MTF01 - Sensor ultrasonico', 3)
    doc.add_paragraph(
        'El MTF01 mide distancia por ultrasonido en un rango de 2cm a 4m con precision de ±1cm. '
        'Esta montado al frente del dron y se utiliza para deteccion de obstaculos en la '
        'trayectoria de vuelo.'
    )
    add_b(doc, 'Protocolo: I2C a direccion 0x57 en el bus 1 de la RPi4', bold_prefix='Conexion: ')
    add_b(doc, 'Lectura de 2 bytes desde el registro 0x01; distancia = raw / 58.0 (cm)', bold_prefix='Lectura: ')
    add_b(doc, '20 lecturas por segundo, gestionado por SensorManager', bold_prefix='Frecuencia: ')
    doc.add_paragraph(
        'En la app, la distancia del MTF01 se muestra en la pantalla de telemetria. '
        'Si la distancia es menor a 2m, el sistema activa la alerta de obstaculo al frente. '
        'Si es menor a 1m, el sistema de navegacion autonoma frena el dron (modo BRAKE).'
    )

    add_h(doc, '4.2 YDLIDAR X4PRO - Laser 360°', 3)
    doc.add_paragraph(
        'El YDLIDAR X4PRO realiza un escaneo laser de 360 grados alrededor del dron, '
        'generando 720 puntos por revolucion (resolucion angular de 0.5°). El rango '
        'de deteccion es de 0.12m a 10m.'
    )
    add_b(doc, 'USB/serial a 115200 baud, aparece como /dev/ttyUSB0', bold_prefix='Conexion: ')
    add_b(doc, 'Paquetes de 5 bytes: angulo (2B), distancia (2B), calidad (1B)', bold_prefix='Protocolo: ')
    add_b(doc, '5-12 Hz (escaneos completos por segundo)', bold_prefix='Frecuencia: ')
    doc.add_paragraph(
        'Los datos del YDLIDAR se usan para construir el mapa de obstaculos '
        'alrededor del dron. Cada punto del escaneo se proyecta en una cuadricula '
        '2D de 20x20m con resolucion de 0.2m.'
    )

    add_h(doc, '4.3 Mapa de obstaculos', 3)
    doc.add_paragraph(
        'El sistema combina los datos del MTF01 y el YDLIDAR en un mapa de ocupacion '
        '2D en tiempo real. Este mapa es la base para la navegacion autonoma:\n\n'
        '- Dimensiones: 20m x 20m centrado en el dron\n'
        '- Resolucion: 0.2m por celda (100x100 celdas)\n'
        '- Cada celda tiene un valor de ocupacion de 0.0 (libre) a 1.0 (ocupado)\n'
        '- Los obstaculos nuevos incrementan la ocupacion en +0.3\n'
        '- El espacio libre entre el dron y el obstaculo se decrementa en -0.1 (ray casting)\n'
        '- La ocupacion decae con factor 0.995 por ciclo (los obstaculos viejos se "olvidan")\n'
        '- Se puede reiniciar el mapa desde la app'
    )

    # 5
    add_h(doc, '5. Navegacion autonoma', 2)
    doc.add_paragraph(
        'El sistema puede navegar el dron de forma autonoma a un punto GPS o a traves '
        'de una serie de waypoints, evitando obstaculos en tiempo real.'
    )

    add_h(doc, '5.1 Modos de navegacion', 3)
    add_tbl(doc, ['Modo', 'Descripcion', 'Activacion'], [
        ['IDLE', 'En espera, sin navegacion activa', 'Por defecto al iniciar'],
        ['NAVIGATING', 'Navegando a un punto GPS', 'navGoto(lat, lon, alt)'],
        ['MISSION', 'Ejecutando mision con waypoints', 'navMission(waypoints)'],
        ['AVOIDING', 'Esquivando obstaculo, pausa temporal', 'Automatico al detectar obstaculo'],
    ])

    add_h(doc, '5.2 Algoritmo de evitacion', 3)
    doc.add_paragraph(
        'El sistema de evitacion funciona en dos niveles de distancia:\n\n'
        'Distancia de seguridad (2m):\n'
        '- Cuando un obstaculo esta entre 1m y 2m, el sistema calcula una direccion '
        'libre y ajusta el rumbo del dron para evitarlo\n'
        '- La direccion libre se busca probando angulos: 0°, ±30°, ±60°, ±90°, ±120°, 180°\n'
        '- Se verifica que haya espacio libre de al menos 2m en cada direccion\n\n'
        'Distancia critica (1m):\n'
        '- Cuando un obstaculo esta a menos de 1m, el dron frena inmediatamente '
        '(modo BRAKE) y espera 3 segundos antes de reintentar\n'
        '- Si el BRAKE falla, se intenta LOITER como respaldo\n\n'
        'El sistema de evitacion se puede activar/desactivar desde la app en cualquier momento.'
    )

    add_h(doc, '5.3 Planificador de rutas', 3)
    doc.add_paragraph(
        'Cuando se envia el dron a un destino, el planificador:\n'
        '1. Divide la trayectoria en segmentos de 2m\n'
        '2. Verifica si cada segmento pasa por una celda ocupada del mapa\n'
        '3. Si hay obstaculo, busca un desvio hacia la direccion libre mas cercana\n'
        '4. Genera los waypoints intermedios y los envia al controlador\n\n'
        'Tambien soporta patrones de busqueda en espiral para inspeccion de areas, '
        'con paso configurable y maximo de 50 waypoints.'
    )

    add_h(doc, '5.4 Comandos desde la app', 3)
    doc.add_paragraph(
        'Desde la app puedes controlar la navegacion autonoma:\n\n'
        '- Iniciar navegacion a coordenada: ingresa latitud, longitud y altitud\n'
        '- Iniciar mision: define una lista de waypoints\n'
        '- Detener navegacion: el dron se detiene y entra en IDLE\n'
        '- Activar/desactivar evitacion de obstaculos\n'
        '- Ver el mapa de obstaculos en tiempo real\n'
        '- Reiniciar el mapa de obstaculos'
    )

    # 6
    add_h(doc, '6. Modo SIM y modo DEMO', 2)
    doc.add_paragraph(
        'El sistema esta disenado para funcionar sin hardware real durante el desarrollo y las pruebas.'
    )

    add_h(doc, '6.1 Modo SIM (Backend)', 3)
    doc.add_paragraph(
        'Cuando el servidor no detecta dispositivos MAVLink ni sensores conectados, '
        'entra automaticamente en modo SIM:\n\n'
        '- Dron simulado: responde a todos los comandos (arm, takeoff, land, goto, etc.)\n'
        '- GPS simulado: coordenadas cerca de Bogotá (4.7110, -74.0721) con movimiento sinusoidal\n'
        '- MTF01 simulado: distancia sinusoidal de 1.5m ± 1m, variando a 0.3 rad/s\n'
        '- YDLIDAR simulado: 720 puntos por escaneo con 4 obstaculos ficticios a 45°, 120°, 200°, 300°\n'
        '- Bateria simulada: disminuye lentamente con el tiempo\n'
        '- Actitud simulada: cambios suaves en roll, pitch, yaw'
    )

    add_h(doc, '6.2 Modo DEMO (App movil)', 3)
    doc.add_paragraph(
        'Si la app no puede conectarse al servidor WebSocket tras 5 segundos, '
        'activa el modo DEMO local:\n\n'
        '- Genera datos de telemetria simulados localmente en el telefono\n'
        '- Todos los comandos se ejecutan localmente con respuestas simuladas\n'
        '- Incluye sensores MTF01 y YDLIDAR simulados\n'
        '- Comandos de navegacion simulados (navGoto, navMission, navStop, setAvoidance)\n'
        '- Ideal para demostraciones y pruebas sin el dron'
    )

    # 7
    add_h(doc, '7. Seguridad y emergencias', 2)
    doc.add_paragraph(
        'El sistema implementa multiples niveles de seguridad para proteger el dron:'
    )
    add_b(doc, 'STOP: Cambia a modo BRAKE (frena en el aire). Si BRAKE falla, usa LOITER', bold_prefix='Parada de emergencia: ')
    add_b(doc, 'RTL: Return To Launch, el dron regresa al punto de despegue y aterriza', bold_prefix='Retorno automatico: ')
    add_b(doc, 'LAND: Aterrizaje inmediato en la posicion actual', bold_prefix='Aterrizaje forzoso: ')
    add_b(doc, 'KILL: Detiene todos los motores inmediatamente (uso exclusivo para emergencias graves)', bold_prefix='Parada de motores: ')
    add_b(doc, 'Si se pierde la conexion con el dron, el backend lo detecta en menos de 5 segundos', bold_prefix='Monitor de conexion: ')
    add_b(doc, 'El BRAKE tiene cooldown de 3s para evitar comandos repetitivos', bold_prefix='Anti-rebote: ')
    add_b(doc, 'La vision por computadora (YOLOv8) activa BRAKE si detecta objeto a menos de 2m', bold_prefix='Vision de seguridad: ')

    # 8
    add_h(doc, '8. Camara y vision artificial', 2)
    doc.add_paragraph(
        'Opcionalmente, el sistema integra una camara (RealSense D435i o webcam USB) para '
        'transmision de video en vivo y deteccion de objetos con YOLOv8:\n\n'
        '- Resolucion: 640x480 a 30 fps\n'
        '- Streaming por WebSocket a 25 fps (imagenes JPEG base64)\n'
        '- Streaming MJPEG para navegador web\n'
        '- Deteccion de 80 clases de objetos (COCO dataset)\n'
        '- Estimacion de distancia basada en altura conocida de objetos\n'
        '- Zonas de seguridad: safe (>5m), warning (>2m), critical (<2m)\n'
        '- La deteccion en zona critica activa automaticamente el frenado de emergencia'
    )

    # 9
    add_h(doc, '9. Especificaciones tecnicas', 2)
    add_tbl(doc, ['Parametro', 'Valor'], [
        ['Frecuencia de telemetria', '10 Hz (WebSocket broadcast)'],
        ['Frecuencia de sensores', '20 Hz (MTF01 + YDLIDAR + mapa)'],
        ['Frecuencia de navegacion', '5 Hz (loop autonomo)'],
        ['Frecuencia de RC', '10 Hz (envio de override)'],
        ['Lectura MAVLink', '100 Hz (loop de recepcion)'],
        ['Rango MTF01', '2 cm - 4 m (±1 cm)'],
        ['Rango YDLIDAR', '0.12 m - 10 m (360°, 720 pts)'],
        ['Mapa de obstaculos', '20 x 20 m, resolucion 0.2 m'],
        ['Distancias de seguridad', '2 m (alerta) / 1 m (freno)'],
        ['Cooldown de BRAKE', '3 segundos'],
        ['Consumo de RAM (backend)', '< 200 MB sin camara'],
        ['Consumo de CPU (backend)', '< 30% en RPi4 sin camara'],
        ['Latencia de comandos', '< 100 ms (red local)'],
    ])

    # 10
    add_h(doc, '10. Verificacion del sistema (25-Mayo-2026)', 2)
    doc.add_paragraph(
        'Se realizaron pruebas integrales del sistema completo en modo SIM para verificar '
        'el funcionamiento correcto de todos los modulos:'
    )
    add_tbl(doc, ['Prueba', 'Resultado', 'Detalle'], [
        ['Arranque del servidor', 'OK', 'Inicializacion completa sin errores'],
        ['Conexion MAVLink SIM', 'OK', 'MAVController en modo simulado'],
        ['Sensor MTF01', 'OK', 'Distancia sinusoidal 0.5-2.5m, 20 Hz'],
        ['Sensor YDLIDAR', 'OK', '720 puntos/escaneo, 4 obstaculos simulados'],
        ['Mapa de obstaculos', 'OK', 'Grilla 20x20m con datos de ambos sensores'],
        ['Evitacion de obstaculos', 'OK', 'BRAKE a <1m, AVOID a <2m, cooldown 3s'],
        ['Navegacion goto', 'OK', 'Cambio a modo NAVIGATING con coordenadas'],
        ['Navegacion stop', 'OK', 'Vuelta a modo IDLE correctamente'],
        ['WebSocket telemetria', 'OK', 'Broadcast a 10Hz con datos de sensores'],
        ['API REST /api/sensors', 'OK', 'Respuesta JSON con mtf01, lidar, mapa'],
        ['API REST /api/nav/status', 'OK', 'Estado IDLE con avoidance activo'],
        ['API REST /api/obstacle-map', 'OK', 'Grilla 20x20m con downsampling'],
        ['Compilacion APK', 'OK', 'APK debug 115 MB, 128 tareas gradle'],
    ])

    # 11
    add_h(doc, '11. Resolucion de problemas', 2)
    add_tbl(doc, ['Problema', 'Causa posible', 'Solucion'], [
        ['El servidor no arranca', 'Puerto 8000 ocupado', 'Cambiar puerto en configuracion'],
        ['No se conecta al Pixhawk', 'USB no conectado o permisos', 'Verificar cable, agregar usuario a dialout'],
        ['Sensores no disponibles', 'Hardware no conectado', 'Verificar I2C (i2cdetect) y USB (lsusb)'],
        ['La app no se conecta', 'IP incorrecta', 'Verificar IP del servidor en config app'],
        ['Video no funciona', 'Camara no detectada', 'Verificar conexion USB de la camara'],
        ['GPS sin datos', 'Sin satelites o en interior', 'Esperar en exterior, verificar fix'],
        ['Navegacion no inicia', 'Dron no armado', 'Armar el dron primero (ARM)'],
        ['Errores I2C', 'Conexion incorrecta', 'Verificar pines SDA/SCL, distancia de cables'],
    ])

    add_sep(doc)
    p_fin = doc.add_paragraph()
    add_run(p_fin, '--- Fin del Manual de Usuario ---', italic=True, color=GRIS, size=9)

    dst = os.path.join(OUT_DIR, 'Copia de MANUAL DE USUARIO.docx')
    doc.save(dst)
    print(f'  -> {os.path.basename(dst)}')

# ── MANUAL TECNICO ────────────────────────────────────────────
def gen_tecnico():
    doc = Document(); cfg(doc)

    # Portada
    add_h(doc, 'Manual Tecnico', 0)
    add_h(doc, 'Sistema de Control Drone con Sensores', 1)
    add_h(doc, 'y Navegacion Autonoma', 1)
    p = doc.add_paragraph()
    add_run(p, 'Version 1.0.0  |  Mayo 2026', italic=True, color=GRIS)
    p2 = doc.add_paragraph()
    add_run(p2, 'Documentacion tecnica del proyecto: back-mavlink', italic=True, color=GRIS)
    doc.add_paragraph()

    # 1
    add_h(doc, '1. Introduccion', 2)
    doc.add_paragraph(
        'El presente documento describe la arquitectura, diseno e implementacion del sistema '
        'de control y telemetria para drones "back-mavlink". Se trata de una plataforma de '
        'codigo abierto que integra un backend en Python (FastAPI) con una aplicacion movil '
        'en React Native, utilizando el protocolo MAVLink para la comunicacion con el '
        'controlador de vuelo (Pixhawk/ArduPilot).'
    )

    doc.add_paragraph(
        'El sistema incorpora tres sensores principales para la percepcion del entorno:\n'
        '- MTF01: sensor ultrasonico para deteccion de obstaculos frontales\n'
        '- YDLIDAR X4PRO: laser de barrido 360° para mapeo de obstaculos perimetrales\n'
        '- RealSense D435i o webcam USB: vision artificial con YOLOv8\n\n'
        'Estos sensores alimentan un modulo de navegacion autonoma que permite al dron '
        'desplazarse a waypoints evitando obstaculos en tiempo real.'
    )

    add_h(doc, '1.1 Stack tecnologico', 2)
    add_tbl(doc, ['Componente', 'Tecnologia', 'Version'], [
        ['Backend', 'Python + FastAPI + Uvicorn', '3.12 / 0.104 / 0.24'],
        ['Comunicacion drone', 'pymavlink', '2.4.41'],
        ['Base de datos', 'PostgreSQL 15 (opcional)', '15'],
        ['Sensores I2C', 'smbus / smbus2', '-'],
        ['Sensores serial', 'pyserial', '3.5'],
        ['Vision artificial', 'OpenCV + YOLOv8n', '4.8.1'],
        ['App movil', 'React Native + TypeScript', '0.83.1'],
        ['Mapas', 'react-native-maps', '1.27.1'],
        ['Contenedores', 'Docker + docker-compose', '-'],
    ])

    add_h(doc, '1.2 Estructura del proyecto', 2)
    add_code_block(doc,
        'back-mavlink/\n'
        '  backend/\n'
        '    main.py              # Punto de entrada FastAPI\n'
        '    config.py            # Variables de entorno y auto-deteccion\n'
        '    mavlink/\n'
        '      controller.py      # MAVController (facade principal)\n'
        '      connection.py      # MAVLinkConnection (gestion de conexion)\n'
        '      commands.py        # DroneCommands (envio de comandos MAVLink)\n'
        '      telemetry.py       # DroneTelemetry (lectura de datos)\n'
        '      rc_override.py     # RCOverrideController (control RC)\n'
        '      geo_utils.py       # Utilidades de conversion GPS\n'
        '    sensors/\n'
        '      base.py            # Clase abstracta BaseSensor + dataclasses\n'
        '      mtf01.py           # Driver MTF01 (I2C addr 0x57)\n'
        '      ydlidar_x4.py      # Driver YDLIDAR X4PRO (USB serial)\n'
        '      obstacle_map.py    # Mapa de ocupacion 2D\n'
        '      manager.py         # SensorManager (loop 20 Hz)\n'
        '    navigation/\n'
        '      avoidance.py       # ObstacleAvoidance (evitacion)\n'
        '      planner.py         # PathPlanner (planificador de rutas)\n'
        '      controller.py      # NavigationController (loop 5 Hz)\n'
        '    api/\n'
        '      rest.py            # Endpoints REST\n'
        '      websocket.py       # WebSocket de telemetria\n'
        '      camera_stream.py   # Streaming de video\n'
        '    vision/\n'
        '      detector.py        # Detector YOLOv8\n'
        '    db/\n'
        '      database.py        # Conexion PostgreSQL\n'
        '      models.py          # Modelo SQLAlchemy\n'
        '      repository.py      # Operaciones CRUD\n'
        '    assets/models/       # Pesos de YOLOv8\n'
        '  mobile/\n'
        '    src/\n'
        '      App.tsx            # Componente raiz\n'
        '      config.ts          # Configuracion de red\n'
        '      context/\n'
        '        DroneContext.tsx  # Contexto global + WebSocket + DEMO\n'
        '      screens/\n'
        '        DroneControlScreen.tsx  # Pantalla principal\n'
        '        GPSScreen.tsx           # Mapa GPS\n'
        '        TelemetryScreen.tsx     # Datos de telemetria\n'
        '        WaypointScreen.tsx      # Gestion de waypoints\n'
        '      components/\n'
        '        Joystick.tsx     # Joystick virtual\n'
        '        StatusBar.tsx    # Barra de estado\n'
        '        TacticalButton.tsx # Botones animados\n'
        '  scripts/\n'
        '    actualizar_docs.py   # Generador de documentacion\n'
        '  documentacion/         # Documentos generados\n'
        '  docker-compose.yml     # Orquestacion Docker\n'
        '  Dockerfile             # Imagen del backend'
    )

    # 2
    add_h(doc, '2. Arquitectura del backend', 2)
    doc.add_paragraph(
        'El backend sigue una arquitectura modular basada en el patron de diseno Facade. '
        'El modulo central es MAVController, que actua como fachada unificada para todas '
        'las operaciones del dron, ocultando la complejidad de los modulos subyacentes '
        '(conexion, comandos, telemetria, control RC).'
    )

    add_h(doc, '2.1 MAVController (controller.py)', 2)
    doc.add_paragraph(
        'MAVController es el punto de entrada principal para toda interaccion con el dron. '
        'Implementa un patron de delegacion: en modo real, redirige cada metodo a los objetos '
        'internos MAVLinkConnection, DroneCommands, DroneTelemetry y RCOverrideController. '
        'En modo SIM, redirige todos los metodos a _SimulatedController, que genera datos '
        'sinteticos realistas sin hardware.'
    )
    add_tbl(doc, ['Metodo', 'Parametros', 'Descripcion', 'Modo SIM'], [
        ['arm()', 'force: bool', 'Arma los motores', 'Simulado'],
        ['disarm()', 'force: bool', 'Desarma los motores', 'Simulado'],
        ['set_mode()', 'mode: str', 'Cambia modo de vuelo', 'Simulado'],
        ['takeoff()', 'altitude: float', 'Despegue autonomo', 'Simulado'],
        ['land()', '-', 'Aterrizaje', 'Simulado'],
        ['rtl()', '-', 'Retorno a casa', 'Simulado'],
        ['goto_position()', 'lat, lon, alt', 'Navegar a coordenada', 'Simulado'],
        ['goto()', 'lat, lon, alt', 'Alias de goto_position', 'Simulado'],
        ['return_to_launch()', '-', 'Alias de rtl', 'Simulado'],
        ['kill_motors()', '-', 'Parada de emergencia', 'Simulado'],
        ['upload_mission()', 'waypoints: list', 'Subir mision de waypoints', 'Simulado'],
        ['start_mission()', '-', 'Iniciar mision en AUTO', 'Simulado'],
        ['clear_mission()', '-', 'Limpiar mision', 'Simulado'],
        ['set_param()', 'name, value', 'Configurar parametro', 'Simulado'],
        ['get_param()', 'name', 'Leer parametro', 'Simulado'],
        ['is_connected()', '-', 'Estado de conexion', 'Siempre True'],
        ['is_armed()', '-', 'Estado de armado', 'Del estado simulado'],
        ['get_mode()', '-', 'Modo actual', 'Del estado simulado'],
        ['get_system_status()', '-', 'Estado del sistema', 'Del estado simulado'],
    ])

    add_h(doc, '2.1.1 _SimulatedController', 3)
    doc.add_paragraph(
        'El simulador interno ejecuta un bucle en segundo plano a 10 Hz que:\n'
        '- Incrementa la altitud cuando el dron esta armado en modo GUIDED\n'
        '- Disminuye la bateria lentamente (simula consumo)\n'
        '- Mantiene posicion GPS cerca de Bogota (4.7110, -74.0721)\n'
        '- Genera movimientos sinusoidales en actitud (roll, pitch, yaw)\n'
        '- Almacena waypoints de mision simulados\n'
        '- Responde a todos los comandos como si el dron estuviera conectado'
    )

    add_h(doc, '2.2 MAVLinkConnection (connection.py)', 2)
    doc.add_paragraph(
        'Gestiona la conexion serial/TCP/UDP con el controlador de vuelo:\n\n'
        '- Conexion mediante mavutil.mavlink_connection() con source_system=255\n'
        '- Timeout de heartbeat: 10 segundos\n'
        '- Reintentos con backoff exponencial: 2^(attempt-1) segundos\n'
        '- Hilo de auto-reconexion en segundo plano (intervalo configurable)\n'
        '- Lock exclusivo para operaciones de escritura (prevencion de condicion de carrera)\n'
        '- Cola de mensajes COMMAND_ACK para confirmacion de comandos\n'
        '- Cola de mensajes MISSION_* para protocolo de mision\n'
        '- Evento de pausa para evitar lecturas durante subida de mision\n'
        '- Timeout de 3s para wait_ack(), polling cada 50ms'
    )

    add_h(doc, '2.3 DroneTelemetry (telemetry.py)', 2)
    doc.add_paragraph(
        'Ejecuta un bucle de lectura a 100 Hz que procesa los mensajes MAVLink entrantes '
        'y los almacena en un diccionario central (self.data). Los mensajes procesados son:'
    )
    add_tbl(doc, ['Mensaje MAVLink', 'Campos extraidos', 'Frecuencia'], [
        ['VFR_HUD', 'altitude, airspeed, climb_rate, throttle', 'Tipicamente 5 Hz'],
        ['GPS_RAW_INT', 'lat, lon, alt, satellites, fix_type, hdop', 'Tipicamente 5 Hz'],
        ['BATTERY_STATUS', 'voltages[], current_battery, battery_remaining', 'Tipicamente 2 Hz'],
        ['SYS_STATUS', 'voltage_battery, current_battery (fallback)', 'Tipicamente 2 Hz'],
        ['ATTITUDE', 'roll, pitch, yaw (convertidos a grados)', 'Tipicamente 10 Hz'],
        ['HEARTBEAT', 'armed (base_mode), mode, system_status', 'Tipicamente 1 Hz'],
        ['HOME_POSITION', 'lat, lon, alt', 'Una vez al arrancar'],
    ])
    doc.add_paragraph(
        'Ademas, el modulo de telemetria incluye:\n'
        '- Persistencia opcional a PostgreSQL cada 5 segundos\n'
        '- Funcion preflight_checks() que verifica: GPS fix>=3, satelites>=6, bateria>30%, EKF OK, home_position valida\n'
        '- Mapeo de modos ArduCopter: convierte custom_mode (0-23) a nombres de modo (STABILIZE, AUTO, GUIDED, etc.)\n'
        '- Calculo de tiempo restante de bateria basado en capacidad nominal (5000 mAh) y consumo actual'
    )

    add_h(doc, '2.4 DroneCommands (commands.py)', 2)
    doc.add_paragraph(
        'Cada comando utiliza el lock de conexion para envio thread-safe, seguido de '
        'wait_ack() para confirmacion. Los comandos MAVLink implementados son:'
    )
    add_tbl(doc, ['Metodo', 'Comando MAVLink', 'Detalle'], [
        ['arm', 'MAV_CMD_COMPONENT_ARM_DISARM', 'param1=1, param2=21196 si force'],
        ['disarm', 'MAV_CMD_COMPONENT_ARM_DISARM', 'param1=0'],
        ['takeoff', 'MAV_CMD_NAV_TAKEOFF', 'Cambia a GUIDED, arma si es necesario'],
        ['land', 'MAV_CMD_NAV_LAND', 'Aterrizaje autonomo'],
        ['goto_position', 'SET_POSITION_TARGET_GLOBAL_INT', 'Frame GLOBAL_RELATIVE_ALT_INT, mask 0xDF8'],
        ['set_velocity', 'SET_POSITION_TARGET_LOCAL_NED', 'Control de velocidad en cuerpo'],
        ['emergency_stop', 'Escalado', 'RTL -> LAND -> DISARM'],
        ['kill_motors', 'MAV_CMD_COMPONENT_ARM_DISARM', 'disarm(force=True) directo'],
        ['reboot_autopilot', 'MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN', 'param1=1'],
        ['set_mode', 'master.set_mode()', 'Usa mode_mapping() del mavutil'],
    ])

    add_h(doc, '2.5 RCOverrideController (rc_override.py)', 2)
    doc.add_paragraph(
        'Permite el control manual del dron mediante la sobreescritura de canales RC. '
        'Los valores se normalizan (-1.0 a 1.0) y se convierten a PWM (1000-2000):\n\n'
        '- Para roll, pitch, yaw: PWM = 1500 + valor * 500\n'
        '- Para throttle: PWM = 1000 + valor * 1000\n\n'
        'El envio se realiza en un hilo separado a 10 Hz mediante el mensaje '
        'RC_CHANNELS_OVERRIDE de MAVLink. Al detenerse, se envian todos los canales '
        'en cero para liberar el override.'
    )

    add_h(doc, '2.6 GeoUtils (geo_utils.py)', 2)
    doc.add_paragraph(
        'Proporciona funciones de conversion entre coordenadas relativas (cuerpo del dron) '
        'y coordenadas GPS absolutas:\n\n'
        '- relative_to_gps(): Convierte offset (forward, right, up) en el sistema de '
        'coordenadas del dron a latitud/longitud/altitud absolutas\n'
        '- Aplica rotacion de yaw: dx = forward*cos(yaw) - right*sin(yaw)\n'
        '- Factor de conversion: 1° latitud = 111320m, 1° longitud = 111320*cos(lat) m\n'
        '- waypoints_relative_to_gps(): Convierte lista de waypoints relativos a absolutos'
    )

    # 3
    add_h(doc, '3. Modulo de sensores (backend/sensors/)', 2)
    doc.add_paragraph(
        'El modulo de sensores sigue una arquitectura orientada a objetos con una clase '
        'base abstracta y dos implementaciones concretas. Un manager central orquesta '
        'las lecturas en un bucle dedicado.'
    )

    add_h(doc, '3.1 Clase BaseSensor (base.py)', 3)
    doc.add_paragraph(
        'Clase abstracta que define la interfaz comun para todos los sensores:\n\n'
        '- Atributos: name (str), sim_mode (bool), _running (bool), _error_count (int)\n'
        '- Metodos abstractos: start() -> bool, stop(), read() -> SensorReading\n'
        '- Propiedades: is_running, status (dict con name, running, sim_mode, errors)\n\n'
        'Dataclasses comunes:\n'
        '- SensorReading: timestamp (float), valid (bool)\n'
        '- DistanceReading(SensorReading): distance_m (float)\n'
        '- LidarPoint: angle_deg (float), distance_m (float), quality (int)\n'
        '- LidarScan(SensorReading): points (list[LidarPoint]), min_angle, max_angle'
    )

    add_h(doc, '3.2 MTF01Sensor (mtf01.py)', 3)
    add_tbl(doc, ['Parametro', 'Valor'], [
        ['Rango de medicion', '2 cm - 4 m'],
        ['Precision', '±1 cm'],
        ['Protocolo', 'I2C, direccion 0x57, bus 1'],
        ['Registro de lectura', '0x01, 2 bytes (big-endian)'],
        ['Formula de conversion', 'distancia_cm = raw / 58.0'],
        ['Frecuencia', '20 Hz (gestionado por SensorManager)'],
    ])
    doc.add_paragraph('Modo real: Lee 2 bytes del registro 0x01 via smbus.SMBUS, '
        'convierte raw a centimetros usando la formula distancia = raw / 58.0.')
    doc.add_paragraph('Modo sim: Genera distancia sinusoidal: 1.5 + 1.0 * sin(elapsed * 0.3) metros, '
        'limitado al rango [0.02, 4.0] metros.')

    add_h(doc, '3.3 YDLidarX4 (ydlidar_x4.py)', 3)
    add_tbl(doc, ['Parametro', 'Valor'], [
        ['Rango de medicion', '0.12 m - 10 m'],
        ['Campo de vision', '360°'],
        ['Puntos por escaneo', '720 (resolucion 0.5°)'],
        ['Frecuencia de escaneo', '5 - 12 Hz'],
        ['Protocolo', 'Serial USB a 115200 baud'],
        ['Formato de paquete', '5 bytes: angulo(2B) | distancia(2B) | calidad(1B)'],
    ])
    doc.add_paragraph('Modo real: Lee paquetes de 5 bytes del puerto serial. '
        'Angulo = (byte0 | byte1<<8) / 64.0 grados, distancia = (byte2 | byte3<<8) mm.')
    doc.add_paragraph('Modo sim: Genera 720 puntos por escaneo con 4 obstaculos '
        'simulados en angulos fijos (45°, 120°, 200°, 300°). Cada obstaculo tiene '
        'una forma gaussiana que reduce la distancia detectada. Se anade ruido '
        'Gaussiano (sigma 0.05m en distancia, sigma 10 en calidad). '
        'La calidad se calcula como max(0, min(255, 150 - (dist/10)*100 + noise)).')

    add_h(doc, '3.4 ObstacleMap (obstacle_map.py)', 3)
    add_tbl(doc, ['Parametro', 'Valor'], [
        ['Dimension del mapa', '20 x 20 metros'],
        ['Resolucion', '0.2 m por celda'],
        ['Celdas', '100 x 100 (col x rows)'],
        ['Centro', '50, 50 (posicion del dron)'],
        ['Valores de ocupacion', '0.0 (libre) a 1.0 (ocupado)'],
        ['Incremento por obstaculo', '+0.3 (LiDAR), +0.5 (ultrasonido)'],
        ['Decremento por espacio libre', '-0.1 (ray casting)'],
        ['Factor de decaimiento', '0.995 por ciclo'],
        ['Umbral de bloqueo', '0.5'],
    ])
    doc.add_paragraph(
        'El mapa de obstaculos actualiza su grilla interna a partir de dos fuentes:\n\n'
        'update_from_lidar(points, drone_yaw):\n'
        '  - Rota cada punto del escaneo por el yaw actual del dron\n'
        '  - Convierte coordenadas polares (distancia, angulo) a cartesianas (x, y)\n'
        '  - Incrementa la ocupacion de la celda objetivo en +0.3\n'
        '  - Aplica ray casting (Bresenham) entre el origen y el punto, decrementando '
        '  las celdas intermedias en -0.1 (el espacio libre se marca como despejado)\n\n'
        'update_from_ultrasonic(distance, drone_yaw):\n'
        '  - Similar al LiDAR pero con un solo punto al frente del dron\n'
        '  - Incremento de +0.5 por deteccion\n\n'
        'find_free_direction(drone_yaw, min_clearance=2.0):\n'
        '  - Prueba direcciones: 0°, ±30°, ±60°, ±90°, ±120°, 180°\n'
        '  - Para cada direccion, verifica que todas las celdas hasta 2m esten libres\n'
        '  - Retorna la primera direccion libre o drone_yaw + 180° como fallback\n\n'
        'to_dict():\n'
        '  - Exporta el mapa downsampeado (cada 10 celdas) con obstaculos > 0.5\n'
        '  - Limitado a 200 obstaculos maximos para evitar payloads grandes'
    )

    add_h(doc, '3.5 SensorManager (manager.py)', 3)
    doc.add_paragraph(
        'El SensorManager es el orquestador central de todos los sensores. '
        'Ejecuta un bucle en un hilo separado (daemon) a 20 Hz (50ms de sleep):\n\n'
        '1. Lectura del MTF01: obtiene distancia frontal\n'
        '2. Lectura del YDLIDAR: obtiene escaneo completo de 720 puntos\n'
        '3. Actualizacion del mapa de obstaculos desde el LiDAR\n'
        '4. Actualizacion del mapa de obstaculos desde el ultrasonico\n'
        '5. Decaimiento de la ocupacion: grid *= 0.995\n'
        '6. Sleep de 50ms\n\n'
        'El manager expone:\n'
        '- get_data(): dict con mtf01, lidar, obstacle_map, drone_yaw\n'
        '- get_status(): dict con estado de cada sensor\n'
        '- has_obstacle_ahead(threshold=2.0): bool - verifica MTF01 y LiDAR frontal\n'
        '- safe_direction: float - direccion libre calculada desde el mapa\n\n'
        'La sincronizacion se realiza mediante threading.Lock para acceso thread-safe '
        'a los datos mas recientes.'
    )

    # 4
    add_h(doc, '4. Modulo de navegacion (backend/navigation/)', 2)
    doc.add_paragraph(
        'El modulo de navegacion implementa la logica de alto nivel para el desplazamiento '
        'autonomo del dron, combinando planificacion de rutas, evitacion de obstaculos y '
        'control de mision en un bucle de control unificado.'
    )

    add_h(doc, '4.1 ObstacleAvoidance (avoidance.py)', 3)
    doc.add_paragraph(
        'Implementa la logica de evitacion reactiva basada en dos umbrales de distancia:'
    )
    add_tbl(doc, ['Estado', 'Distancia', 'Accion', 'Cooldown'], [
        ['CRITICAL', '< 1.0 m (brake_distance)', 'BRAKE: cambia modo a BRAKE, callback emergencia', '3s'],
        ['WARNING', '1.0 - 2.0 m (safety_distance)', 'AVOID: calcula direccion libre, ajusta rumbo', 'No'],
        ['CLEAR', '> 2.0 m', 'NONE: navegacion normal', 'No'],
    ])
    doc.add_paragraph(
        'La evaluacion se realiza en cada ciclo del NavigationController (5 Hz). '
        'El resultado incluye: action (BRAKE/AVOID/NONE), reason, distance, '
        'y para AVOID: turn_deg y safe_heading.'
    )

    add_h(doc, '4.2 PathPlanner (planner.py)', 3)
    doc.add_paragraph(
        'Planifica rutas entre la posicion actual y el destino:\n\n'
        'plan_to_waypoint(start, target, obstacle_map):\n'
        '  - Divide la ruta en segmentos de 2m (step_size)\n'
        '  - Convierte cada waypoint a coordenadas locales relativas al dron\n'
        '  - Verifica si la celda correspondiente en el obstacle_map esta bloqueada\n'
        '  - Si esta bloqueada: busca direccion libre y agrega desvio de 2m\n'
        '  - Retorna lista de waypoints GPS intermedios\n\n'
        'plan_search_pattern(center, radius, spacing):\n'
        '  - Genera patron en espiral: radios crecientes, 12 angulos por anillo (30°)\n'
        '  - Limitado a 50 waypoints\n'
        '  - Ideal para inspeccion de areas'
    )

    add_h(doc, '4.3 NavigationController (controller.py)', 3)
    doc.add_paragraph(
        'Controlador principal de navegacion. Ejecuta un bucle autonomo a 5 Hz '
        '(200ms de sleep) con la siguiente maquina de estados:'
    )
    add_code_block(doc,
        'Estados: IDLE <-> NAVIGATING <-> MISSION\n'
        '                 \\                /\n'
        '                  -> AVOIDING <----\n'
        '                       |\n'
        '                       v (cuando obstaculo despejado)\n'
        '                 NAVIGATING / MISSION'
    )
    doc.add_paragraph(
        'Bucle principal (_nav_loop, 5 Hz):\n'
        '1. Obtiene datos de sensores via sensor_manager.get_data()\n'
        '2. Actualiza el yaw del dron en el sensor manager\n'
        '3. Evalua obstaculos: avoidance.evaluate(sensor_data)\n'
        '   - BRAKE: activa modo BRAKE en el dron, dispara callback de emergencia, '
        '   cambia a estado AVOIDING\n'
        '   - AVOID: registra el rumbo seguro, cambia a AVOIDING\n'
        '   - NONE: si estaba en AVOIDING, vuelve a NAVIGATING/MISSION\n'
        '4. Si estado es NAVIGATING: calcula distancia Haversine al destino, '
        '   si < 2m considera destino alcanzado, sino envia goto()\n'
        '5. Si estado es MISSION: avanza al siguiente waypoint cuando '
        '   distancia < 2m, completa mision cuando no hay mas waypoints\n\n'
        'Formula Haversine implementada: R = 6371000m, distancia = 2*R*asin(sqrt(...))'
    )

    # 5
    add_h(doc, '5. API de comunicacion', 2)
    add_h(doc, '5.1 API REST (rest.py)', 3)
    doc.add_paragraph(
        'El API REST expone 25 endpoints agrupados por funcionalidad. '
        'Todos los endpoints que requieren conexion MAVLink devuelven HTTP 503 '
        'si el controlador no esta disponible. Los schemas de entrada usan Pydantic '
        'con validacion de tipos en runtime.'
    )

    add_h(doc, '5.1.1 Endpoints de estado y telemetria', 3)
    add_tbl(doc, ['Endpoint', 'Metodo', 'Respuesta'], [
        ['/api/status', 'GET', 'connected, armed, mode, system_status'],
        ['/api/telemetry', 'GET', 'armed, mode, altitude, lat, lon, roll, pitch, yaw, battery, speeds, sats, hdop'],
    ])

    add_h(doc, '5.1.2 Endpoints de control basico', 3)
    add_tbl(doc, ['Endpoint', 'Metodo', 'Body (Pydantic)', 'Validaciones'], [
        ['/api/arm', 'POST', 'ArmRequest {force}', 'Ya armado (si !force)'],
        ['/api/disarm', 'POST', '-', 'Ya desarmado'],
        ['/api/takeoff', 'POST', 'TakeoffRequest {altitude}', 'Armado, altitud 2-100m'],
        ['/api/land', 'POST', '-', '-'],
        ['/api/rtl', 'POST', '-', '-'],
        ['/api/mode', 'POST', 'ModeRequest {mode}', 'Modo en VALID_MODES (16)'],
        ['/api/goto', 'POST', 'GotoRequest {lat, lon, alt}', 'Armado'],
    ])

    add_h(doc, '5.1.3 Endpoints de control RC', 3)
    add_tbl(doc, ['Endpoint', 'Metodo', 'Body'], [
        ['/api/rc/control', 'POST', 'RCControlRequest {throttle, yaw, pitch, roll}'],
        ['/api/rc/reset', 'POST', '-'],
        ['/api/rc/values', 'GET', '-'],
    ])

    add_h(doc, '5.1.4 Endpoints de emergencia', 3)
    add_tbl(doc, ['Endpoint', 'Metodo', 'Accion', 'Fallback'], [
        ['/api/emergency', 'POST', 'STOP -> BRAKE', 'LOITER si BRAKE falla'],
        ['/api/emergency', 'POST', 'RTL -> return_to_launch', '-'],
        ['/api/emergency', 'POST', 'LAND -> land', '-'],
        ['/api/emergency', 'POST', 'KILL -> disarm(force)', '-'],
    ])

    add_h(doc, '5.1.5 Endpoints de sensores', 3)
    add_tbl(doc, ['Endpoint', 'Metodo', 'Respuesta'], [
        ['/api/sensors', 'GET', 'mtf01, lidar, obstacle_map, drone_yaw'],
        ['/api/sensors/status', 'GET', 'running, sim_mode, estado individual'],
    ])

    add_h(doc, '5.1.6 Endpoints de navegacion', 3)
    add_tbl(doc, ['Endpoint', 'Metodo', 'Body', 'Descripcion'], [
        ['/api/nav/status', 'GET', '-', 'mode, target, waypoint_index, avoidance_active'],
        ['/api/nav/goto', 'POST', 'NavGotoRequest {lat, lon, alt}', 'Navegacion autonoma'],
        ['/api/nav/mission', 'POST', 'NavMissionRequest {waypoints}', 'Mision con waypoints'],
        ['/api/nav/stop', 'POST', '-', 'Detener navegacion'],
        ['/api/nav/avoidance', 'POST', 'active (query)', 'Activar/desactivar evitacion'],
    ])

    add_h(doc, '5.1.7 Endpoints de mapa de obstaculos', 3)
    add_tbl(doc, ['Endpoint', 'Metodo', 'Descripcion'], [
        ['/api/obstacle-map', 'GET', 'Mapa downsampeado (max 200 obstaculos)'],
        ['/api/obstacle-map/reset', 'POST', 'Reiniciar grilla a 0.0'],
    ])

    add_h(doc, '5.1.8 Endpoints de waypoints', 3)
    add_tbl(doc, ['Endpoint', 'Metodo', 'Descripcion'], [
        ['/api/waypoints/save', 'POST', 'Guarda en data/waypoints/{name}.json'],
        ['/api/waypoints/load', 'POST', 'Carga desde JSON'],
        ['/api/waypoints/list', 'GET', 'Lista conjuntos guardados'],
        ['/api/waypoints/{name}', 'DELETE', 'Elimina conjunto'],
    ])

    add_h(doc, '5.1.9 Endpoints publicos', 3)
    add_tbl(doc, ['Endpoint', 'Metodo', 'Respuesta'], [
        ['/', 'GET', '{message, version, status}'],
        ['/health', 'GET', '{status: healthy}'],
        ['/drones', 'GET', 'Lista de drones (mock)'],
        ['/missions', 'GET', 'Lista de misiones (mock)'],
        ['/users', 'GET', 'Lista de usuarios (mock)'],
        ['/flight-routes', 'GET', 'Lista de rutas (mock)'],
    ])

    add_h(doc, '5.2 API WebSocket (websocket.py)', 3)
    doc.add_paragraph(
        'El servidor WebSocket en /ws/telemetry proporciona comunicacion bidireccional '
        'en tiempo real con la app movil. Utiliza el patron publisher-subscriber '
        'gestionado por ConnectionManager.'
    )

    add_h(doc, '5.2.1 Mensajes salientes (broadcast)', 3)
    doc.add_paragraph(
        'El servidor transmite telemetria a todos los clientes conectados a 10 Hz:'
    )
    add_code_block(doc,
        '{\n'
        '  "type": "telemetry",\n'
        '  "data": {\n'
        '    "armed": false, "mode": "STANDBY",\n'
        '    "altitude": 0.0, "latitude": 4.711, "longitude": -74.0721,\n'
        '    "roll": 0.0, "pitch": 0.0, "yaw": 0.0,\n'
        '    "battery_voltage": 12.5, "battery_current": 0.5,\n'
        '    "battery_remaining": 85, "ground_speed": 0.0,\n'
        '    "vertical_speed": 0.0, "satellites": 10, "hdop": 1.2,\n'
        '    "mtf01_distance": 1.5,\n'
        '    "lidar_closest_distance": 2.3,\n'
        '    "lidar_closest_angle": 45.0,\n'
        '    "lidar_points": 720,\n'
        '    "obstacle_ahead": false\n'
        '  },\n'
        '  "timestamp": "2026-05-25T..."\n'
        '}'
    )

    add_h(doc, '5.2.2 Comandos entrantes', 3)
    add_tbl(doc, ['Comando', 'Parametros', 'Descripcion', 'Requiere ACK'], [
        ['ARM', '{}', 'Armar', 'Si'],
        ['DISARM', '{}', 'Desarmar', 'Si'],
        ['TAKEOFF', '{altitude}', 'Despegar', 'Si'],
        ['LAND', '{}', 'Aterrizar', 'Si'],
        ['RTL', '{}', 'Retorno a casa', 'Si'],
        ['SET_MODE', '{mode}', 'Cambiar modo', 'Si'],
        ['REBOOT', '{}', 'Reiniciar autopiloto', 'Si'],
        ['RC_CONTROL', '{throttle, yaw, pitch, roll}', 'Override RC', 'No'],
        ['RC_RESET', '{}', 'Reset RC', 'No'],
        ['EMERGENCY', '{action}', 'STOP/RTL/LAND', 'Si'],
        ['GOTO', '{lat, lon, alt}', 'Navegar a GPS', 'Si'],
        ['GOTO_RELATIVE', '{forward, right, up}', 'Movimiento relativo', 'Si'],
        ['MISSION_UPLOAD', '{waypoints}', 'Subir waypoints', 'Si'],
        ['MISSION_UPLOAD_RELATIVE', '{waypoints}', 'Waypoints relativos', 'Si'],
        ['START_MISSION', '{}', 'Iniciar mision', 'Si'],
        ['CLEAR_MISSION', '{}', 'Limpiar mision', 'Si'],
        ['SAVE_WAYPOINTS', '{name, waypoints}', 'Persistir waypoints', 'Si'],
        ['LOAD_WAYPOINTS', '{name}', 'Cargar waypoints', 'Si'],
        ['LIST_WAYPOINTS', '{}', 'Listar guardados', 'Si'],
        ['NAV_GOTO', '{lat, lon, alt}', 'Navegacion autonoma', 'Si'],
        ['NAV_MISSION', '{waypoints}', 'Mision autonoma', 'Si'],
        ['NAV_STOP', '{}', 'Detener navegacion', 'Si'],
        ['NAV_AVOIDANCE', '{active}', 'Toggle evitacion', 'Si'],
        ['GET_SENSORS', '{}', 'Datos de sensores', 'Si'],
        ['GET_OBSTACLE_MAP', '{}', 'Mapa de obstaculos', 'Si'],
    ])
    doc.add_paragraph(
        'Formato de respuesta (ACK): {"type": "command_ack", "command": "...", "result": {"success": bool, "message": "..."}}'
    )

    add_h(doc, '5.3 Streaming de video (camera_stream.py)', 3)
    doc.add_paragraph(
        'El modulo de camara proporciona transmision de video en vivo con deteccion '
        'de objetos mediante YOLOv8. Soporta deteccion de 80 clases del dataset COCO '
        'con estimacion de distancia basada en altura conocida de los objetos.\n\n'
        'Endpoints:\n'
        '- WS /api/camera/ws: streaming a 25 fps (JPEG base64)\n'
        '- GET /api/camera/stream: MJPEG para navegador\n'
        '- GET /api/camera/snapshot: un frame JPEG\n'
        '- GET /api/camera/status: estado de camara + vision\n'
        '- GET /api/camera/vision: resultados de deteccion\n\n'
        'La deteccion activa frenado de emergencia si un objeto esta a menos de 2m '
        '(zona critica), con cooldown de 3s.'
    )

    add_h(doc, '5.4 Configuracion (config.py)', 3)
    add_tbl(doc, ['Variable de entorno', 'Default', 'Descripcion'], [
        ['MAVLINK_DEVICE', 'udpin:0.0.0.0:14550', 'Dispositivo MAVLink: SIM, tcp:ip:port, udpin:..., /dev/ttyACM0'],
        ['MAVLINK_BAUD', '115200', 'Baud rate para conexion serie'],
        ['API_HOST', '0.0.0.0', 'Direccion de enlace del servidor'],
        ['API_PORT', '8000', 'Puerto del servidor'],
        ['LOG_LEVEL', 'INFO', 'Nivel de logging (DEBUG, INFO, WARNING, ERROR)'],
        ['DB_URL', 'postgresql://...', 'URL de base de datos PostgreSQL'],
    ])
    doc.add_paragraph(
        'Auto-deteccion de dispositivos MAVLink:\n'
        '1. Si MAVLINK_DEVICE="SIM" -> Modo simulacion\n'
        '2. Si contiene ":" y no empieza con "/" -> Conexion remota TCP/UDP\n'
        '3. Busca en /dev/ttyACM0, ttyACM1, ttyUSB0, ttyUSB1, /dev/serial/by-id/*\n'
        '4. Si no encuentra nada -> Modo SIM (fallback)'
    )

    # 6
    add_h(doc, '6. App movil (React Native)', 2)
    doc.add_paragraph(
        'La aplicacion movil esta desarrollada en React Native 0.83.1 con TypeScript. '
        'Utiliza la nueva arquitectura de React Native (Fabric/TurboModules) con '
        'Hermes como motor de JavaScript.'
    )

    add_h(doc, '6.1 DroneContext (context/DroneContext.tsx)', 3)
    doc.add_paragraph(
        'El contexto global de la aplicacion gestiona:\n\n'
        '- Conexion WebSocket al servidor con auto-reconexion (3s timeout)\n'
        '- Modo DEMO: se activa tras 5s sin conexion, genera datos locales simulados\n'
        '- Heartbeat de RC: envio de RC_CONTROL cada 100ms (10 Hz)\n'
        '- Sistema de comandos con promesas y timeout de 5s\n'
        '- Mapa de comandos pendientes para correlacionar ACKs\n\n'
        'Interfaz Telemetry:\n'
        '- Campos base: armed, mode, altitude, lat, lon, roll, pitch, yaw, battery, speeds, sats, hdop\n'
        '- Campos de sensores: mtf01_distance, lidar_closest_distance, lidar_closest_angle, lidar_points, obstacle_ahead\n\n'
        'Metodos de navegacion:\n'
        '- navGoto(lat, lon, alt?): navegacion autonoma a coordenada\n'
        '- navMission(waypoints): mision con lista de waypoints\n'
        '- navStop(): detener navegacion\n'
        '- setAvoidance(active): activar/desactivar evitacion'
    )

    add_h(doc, '6.2 Pantallas', 3)
    add_tbl(doc, ['Pantalla', 'Archivo', 'Funcion principal'], [
        ['CONTROL', 'DroneControlScreen.tsx (815 L)', 'Video, joysticks, botones tacticos, modos'],
        ['DATA', 'TelemetryScreen.tsx (586 L)', 'Telemetria detallada, horizonte artificial'],
        ['GPS', 'GPSScreen.tsx (568 L)', 'Mapa interactivo con waypoints y ruta'],
        ['ROUTE', 'WaypointScreen.tsx (587 L)', 'Edicion de waypoints, misiones'],
    ])

    add_h(doc, '6.3 Componentes', 3)
    doc.add_paragraph(
        '- Joystick.tsx (263 L): PanResponder personalizado, modo 2 (throttle persistente), '
        'deadzone configurable, animacion de barra de throttle\n'
        '- StatusBar.tsx (160 L): indicadores de conexion, modo, armado, DEMO con animaciones de pulso\n'
        '- TacticalButton.tsx (129 L): efectos de presion con animaciones de escala y color'
    )

    # 7
    add_h(doc, '7. Seguridad y manejo de errores', 2)
    doc.add_paragraph(
        'El sistema implementa multiples capas de seguridad:'
    )
    add_b(doc, 'Escritura thread-safe: todas las operaciones de envio MAVLink usan threading.Lock', bold_prefix='Lock de escritura: ')
    add_b(doc, 'recv_match() NO usa el lock de escritura para evitar deadlocks', bold_prefix='Lectura sin lock: ')
    add_b(doc, 'Colas de mensajes separadas para COMMAND_ACK y MISSION_* ', bold_prefix='Colas de mensajes: ')
    add_b(doc, 'Evento de pausa para evitar interferencias durante subida de mision', bold_prefix='Evento de pausa: ')
    add_b(doc, 'MAVLinkConnection: timeout 10s para heartbeat, backoff exponencial', bold_prefix='Reconexion automatica: ')
    add_b(doc, 'RCOverrideController: al detenerse envia todos los canales a 0', bold_prefix='Liberacion de RC: ')
    add_b(doc, 'EmergencyAction: STOP -> BRAKE -> LOITER (fallback), KILL -> disarm(force)', bold_prefix='Emergencias escalonadas: ')
    add_b(doc, 'ObstacleAvoidance: cooldown de 3s para evitar comandos BRAKE repetitivos', bold_prefix='Anti-rebote: ')
    add_b(doc, 'VisionDetector: cooldown de 3s en deteccion critica', bold_prefix='Vision cooldown: ')
    add_b(doc, 'Modo SIM si no se detecta hardware, modo DEMO si no hay servidor', bold_prefix='Degradacion gradual: ')

    # 8
    add_h(doc, '8. Despliegue', 2)
    add_h(doc, '8.1 Despliegue local (RPi4)', 3)
    add_code_block(doc,
        '# Instalar dependencias del sistema\n'
        'sudo apt update && sudo apt install -y python3-pip i2c-tools\n'
        'sudo raspi-config nonint do_i2c 0  # Habilitar I2C\n'
        'sudo usermod -a -G dialout $USER   # Permisos serial\n'
        '\n'
        '# Clonar e instalar\n'
        'git clone <repo> back-mavlink && cd back-mavlink\n'
        'pip install -r backend/requirements.txt\n'
        '\n'
        '# Ejecutar\n'
        'uvicorn backend.main:app --host 0.0.0.0 --port 8000'
    )

    add_h(doc, '8.2 Despliegue con Docker', 3)
    add_code_block(doc,
        '# Construir y ejecutar con docker-compose\n'
        'docker-compose up --build\n'
        '\n'
        '# Servicios:\n'
        '- postgres:     Puerto 5432\n'
        '- backend:       Puerto 8000\n'
        '- frontend:      Puerto 4545\n'
        '\n'
        '# Nota: el backend se ejecuta en modo privilegiado\n'
        '# para acceder a dispositivos USB (Pixhawk, YDLIDAR)'
    )

    add_h(doc, '8.3 Compilacion del APK', 3)
    add_code_block(doc,
        '# En el directorio mobile/:\n'
        'cd mobile\n'
        'npm install\n'
        'npx react-native build-android --mode=debug\n'
        '\n'
        '# APK generado en:\n'
        'android/app/build/outputs/apk/debug/app-debug.apk\n'
        '\n'
        '# Alternativa con Gradle directamente:\n'
        'cd android\n'
        'set JAVA_HOME=C:\\Program Files\\Microsoft\\jdk-17.0.19.10-hotspot\n'
        'set ANDROID_HOME=C:\\Users\\USUARIO\\AppData\\Local\\Android\\Sdk\n'
        'gradlew.bat assembleDebug'
    )

    # 9
    add_h(doc, '9. Dependencias (requirements.txt)', 2)
    add_code_block(doc,
        'fastapi==0.104.1\n'
        'uvicorn[standard]==0.24.0\n'
        'pymavlink==2.4.41\n'
        'sqlalchemy==2.0.23\n'
        'psycopg2-binary==2.9.9\n'
        'pyserial==3.5\n'
        'python-dotenv==1.0.0\n'
        'pydantic==2.5.0\n'
        'opencv-python-headless==4.8.1.78\n'
        'websockets==11.0.3'
    )

    # 10
    add_h(doc, '10. Verificacion del sistema (25-Mayo-2026)', 2)
    doc.add_paragraph(
        'Se ejecutaron pruebas integrales del sistema completo en modo SIM para validar '
        'el correcto funcionamiento de todos los modulos implementados:'
    )
    add_tbl(doc, ['Modulo', 'Prueba', 'Resultado', 'Observaciones'], [
        ['MAVController', 'Inicializacion SIM', 'OK', 'Controller creado con _sim=True, todos los metodos delegados'],
        ['SensorManager', 'Arranque', 'OK', 'MTF01 y YDLIDAR iniciados en modo simulacion, loop 20Hz'],
        ['MTF01Sensor', 'Lectura simulada', 'OK', 'Distancia sinusoidal 0.5-2.5m a 20Hz'],
        ['YDLidarX4', 'Escaneo simulado', 'OK', '720 puntos/escaneo, 4 obstaculos a 45/120/200/300°'],
        ['ObstacleMap', 'Actualizacion fusionada', 'OK', 'LiDAR+ultrasonido, grilla 100x100 con decaimiento 0.995'],
        ['ObstacleAvoidance', 'Evaluacion de riesgo', 'OK', 'BRAKE a <1m, AVOID a <2m, cooldown 3s funcionando'],
        ['PathPlanner', 'Planificacion con desvio', 'OK', 'Segmentos de 2m, deteccion de celdas bloqueadas, desvio'],
        ['NavigationController', 'Ciclo completo 5Hz', 'OK', 'Estados IDLE/NAVIGATING/MISSION/AVOIDING, emergencia OK'],
        ['REST /api/sensors', 'GET', '200 OK', 'mtf01: {distance_m, valid}, lidar: {points, closest, valid}, mapa'],
        ['REST /api/sensors/status', 'GET', '200 OK', 'running=True, sim_mode=True, errores=0'],
        ['REST /api/nav/status', 'GET', '200 OK', 'mode=IDLE, target=None, avoidance_active=True'],
        ['REST /api/nav/goto', 'POST', '200 OK', 'Cambio a NAVIGATING con coordenadas especificadas'],
        ['REST /api/nav/stop', 'POST', '200 OK', 'Vuelta a IDLE correctamente'],
        ['REST /api/obstacle-map', 'GET', '200 OK', 'Grilla 20x20m downsampeada, <200 obstaculos'],
        ['WebSocket broadcast', 'Telemetria 10Hz', 'OK', 'Datos de sensores incluidos en JSON'],
        ['WebSocket NAV_GOTO', 'Comando + ACK', 'OK', 'Respuesta command_ack con resultado'],
        ['Compilacion APK', 'assembleDebug', 'OK', '115 MB, 128 tareas ejecutadas, 2min 8s'],
    ])

    # 11
    add_h(doc, '11. Trabajo futuro', 2)
    doc.add_paragraph('Mejoras planificadas para versiones futuras:')
    add_b(doc, 'Algoritmo de evasion mas sofisticado (DWA - Dynamic Window Approach)')
    add_b(doc, 'Mapeo 3D del entorno usando datos del YDLIDAR + altitud')
    add_b(doc, 'Rutas de vuelo inteligentes con optimizacion (spline, Bezier)')
    add_b(doc, 'SLAM visual con la camara RealSense para mapeo sin GPS')
    add_b(doc, 'Misiones con puntos de interes y acciones automaticas')
    add_b(doc, 'Grabacion de vuelo y reproduccion (black box)')
    add_b(doc, 'Autenticacion y multiusuario')
    add_b(doc, 'Notificaciones push para alertas de emergencia')
    add_b(doc, 'Soporte para multipleles drones simultaneos')
    add_b(doc, 'Interfaz web como alternativa a la app movil')

    # 12
    add_h(doc, '12. Resumen de archivos', 2)
    add_h(doc, '12.1 Archivos nuevos creados', 3)
    nuevos = [
        'backend/sensors/__init__.py', 'backend/sensors/base.py',
        'backend/sensors/mtf01.py', 'backend/sensors/ydlidar_x4.py',
        'backend/sensors/obstacle_map.py', 'backend/sensors/manager.py',
        'backend/navigation/__init__.py', 'backend/navigation/avoidance.py',
        'backend/navigation/planner.py', 'backend/navigation/controller.py',
    ]
    for f in nuevos:
        add_b(doc, f)

    add_h(doc, '12.2 Archivos modificados', 3)
    modificados = [
        'backend/main.py: inicializa sensores y navegacion en startup/shutdown',
        'backend/api/rest.py: init_sensors, init_navigation, shutdown + 9 endpoints',
        'backend/api/websocket.py: sensores en telemetria broadcast + 6 comandos WS',
        'mobile/src/context/DroneContext.tsx: tipos sensor en Telemetry, 4 metodos navegacion',
    ]
    for f in modificados:
        add_b(doc, f)

    add_sep(doc)
    p_fin = doc.add_paragraph()
    add_run(p_fin, '--- Fin del Manual Tecnico ---', italic=True, color=GRIS, size=9)

    # Guardar
    dst = os.path.join(OUT_DIR, 'MANUAL_TECNICO_APP_DRON.docx')
    doc.save(dst)
    print(f'  -> {os.path.basename(dst)}')

def main():
    print('=== Generando documentacion profesional del proyecto ===\n')
    gen_usuario()
    gen_tecnico()
    print(f'\nDocumentos en {OUT_DIR}:')
    for f in sorted(os.listdir(OUT_DIR)):
        if f.endswith('.docx') or f.endswith('.pdf'):
            sz = os.path.getsize(os.path.join(OUT_DIR, f))
            print(f'  - {f} ({sz/1024:.1f} KB)')

if __name__ == '__main__':
    main()
