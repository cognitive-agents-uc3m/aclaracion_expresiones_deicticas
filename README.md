# Cognitive Agent

Sistema de apoyo para alumnado ciego que detecta referencias visuales en el discurso del profesorado y genera aclaraciones a partir del contenido de las diapositivas.

## Requisitos

- Python 3.12.
- Ollama con el modelo `qwen3:4b-instruct-2507-q4_K_M` para formatear los apuntes.
- Credenciales de Google Cloud con acceso a Vertex AI.
- Una GPU compatible con CUDA para ejecutar Whisper Small con la configuración incluida. También puede utilizarse CPU cambiando `stt.whisper_device` en `config/default.yaml`.

## Instalación

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Configura las credenciales de Google Cloud mediante Application Default Credentials y establece el identificador del proyecto:

```powershell
gcloud auth application-default login
$env:COGNITIVE_AGENT__LLM__GCP_PROJECT="identificador-del-proyecto"
ollama pull qwen3:4b-instruct-2507-q4_K_M
```

## Ejecución

Inicia primero la interfaz del profesor:

```powershell
.\.venv\Scripts\python.exe gui.py
```

La aplicación estará disponible en `http://127.0.0.1:7860`. Desde ella se crea la sesión y se carga la presentación PDF.

Después, abre otra terminal con el mismo entorno virtual e inicia la interfaz del alumno:

```powershell
.\.venv\Scripts\python.exe student_local.py
```

La interfaz del alumno estará disponible en `http://127.0.0.1:7861` y se unirá automáticamente a la sesión activa más reciente.

Para consultar o elegir una sesión concreta:

```powershell
.\.venv\Scripts\python.exe student_local.py --list
.\.venv\Scripts\python.exe student_local.py --session-id IDENTIFICADOR
```

La configuración principal se encuentra en `config/default.yaml`. Los datos generados durante la ejecución se almacenan en `.data/` y no forman parte del repositorio.

## Ejecución con Docker

Docker Compose inicia conjuntamente las interfaces del profesor y del alumno. Ambas comparten un volumen para sincronizar las sesiones y conservar los datos generados.

Crea el fichero de variables de entorno a partir del ejemplo:

```powershell
Copy-Item .env.example .env
```

Edita `.env` e indica el identificador del proyecto de Google Cloud y la ruta del fichero de credenciales generado mediante Application Default Credentials. Después, inicia el sistema:

```powershell
docker compose up --build
```

La interfaz del profesor estará disponible en `http://127.0.0.1:7860`. El servicio del alumno esperará hasta que el profesor cree una sesión y después publicará su interfaz en `http://127.0.0.1:7861`.

La configuración anterior ejecuta Whisper mediante CPU para funcionar sin requisitos adicionales. Si Docker Desktop dispone de acceso a una GPU NVIDIA y está instalado NVIDIA Container Toolkit, puede utilizarse CUDA mediante:

```powershell
docker compose -f compose.yaml -f compose.gpu.yaml up --build
```

Para detener los servicios se utiliza `docker compose down`. Los datos permanecen en el volumen `cognitive-data`. Para eliminarlos también, se utiliza `docker compose down --volumes`.