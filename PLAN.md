# BKPmovil — Plan de proyecto

> **Estado: implementado.** Las fases 0 a 5 están terminadas: motor
> incremental, interfaz de cuatro pasos, guía por fabricante, CLI completa,
> empaquetado con instalador y publicación automática desde GitHub. Ver
> [README.md](README.md) y [docs/GUIA.md](docs/GUIA.md).
>
> Cambios respecto al plan original, con su motivo:
> - La copia se hace **fichero a fichero** en vez de por carpetas enteras.
>   Cuesta algo de rendimiento pero es lo que hace correctos a la vez el
>   progreso en vivo, el pausar/cancelar sin perder nada y el incremental.
> - La reconstrucción del índice recorre **del móvil al disco**, no al revés:
>   el saneado de nombres para Windows no es invertible, así que se aplica la
>   misma función que usó la copia y se comprueba si el fichero está.
> - Las carpetas de mensajería **no usan rutas fijas**: se buscan por nombre
>   en todo el almacenamiento, porque cambian entre versiones de Android.

App de escritorio para hacer copias de seguridad de un móvil Android por
**depuración inalámbrica (ADB sobre WiFi)**, sin cables y sin root, pensada
para uso personal y familiar.

---

## 1. Decisiones tomadas

| Decisión | Elección |
|---|---|
| Stack | Python 3.11+ · **PySide6** (Qt 6) |
| Plataformas | **Linux** (desarrollo/uso principal) y **Windows** (familia) |
| Modo de copia | **Incremental** con índice persistente |
| Selección de carpetas | Lista por defecto **auto-detectada y editable** |
| Distribución | PyInstaller → AppImage (Linux) / `.exe` portable (Windows) |
| ADB | Se usa el del sistema si existe; si no, el binario incluido en el paquete |

---

## 2. Realidad técnica de ADB inalámbrico

Esto condiciona toda la UI del asistente, así que conviene tenerlo claro:

### Android 11 o superior (lo normal hoy)
Hay **dos puertos distintos**, y es el error nº1 de todo el mundo:

1. `Ajustes → Opciones de desarrollador → Depuración inalámbrica`
2. `Vincular dispositivo con código de vinculación` → muestra
   **IP:PUERTO_DE_VINCULACIÓN** y un **código de 6 dígitos**.
   Ese puerto es **temporal y aleatorio**, solo sirve para emparejar.
   → `adb pair 192.168.1.50:37451 123456`
3. La pantalla principal de *Depuración inalámbrica* muestra otra
   **IP:PUERTO** distinto, el permanente de la sesión.
   → `adb connect 192.168.1.50:41233`

El emparejamiento se hace **una sola vez** por ordenador. En copias
posteriores basta el paso 3 (y el puerto suele cambiar al reiniciar el WiFi
o el móvil, por eso la app debe permitir editarlo siempre).

### Android 10 o inferior
No existe la vinculación por código. Requiere **un cable USB una vez**:
`adb tcpip 5555` → desconectar cable → `adb connect IP:5555`.

### Implicación de diseño
El asistente tendrá **dos ramas** (Android ≥11 / Android ≤10) y la app
guardará un perfil por dispositivo (alias, IP, último puerto, ya emparejado
sí/no) para que la segunda vez sea: abrir → *Conectar* → *Copiar*.

---

## 3. Qué se puede copiar sin root (y qué no)

Accesible por `adb pull` sin root:

| Contenido | Ruta en el móvil |
|---|---|
| Cámara, capturas, WhatsApp Images (visibles en galería) | `/sdcard/DCIM` |
| Imágenes de apps, capturas, wallpapers | `/sdcard/Pictures` |
| Vídeos | `/sdcard/Movies` |
| Descargas | `/sdcard/Download` |
| Documentos | `/sdcard/Documents` |
| Música y grabaciones | `/sdcard/Music`, `/sdcard/Recordings` |
| **Media de WhatsApp** (Android 11+) | `/sdcard/Android/media/com.whatsapp/WhatsApp/Media` |
| Media de WhatsApp (Android ≤10) | `/sdcard/WhatsApp/Media` |
| Media de Telegram | `/sdcard/Android/media/org.telegram.messenger/Telegram` |
| Media de Signal | `/sdcard/Signal` |

**NO accesible sin root** (limitación real de Android 11+, no de la app):

- `/sdcard/Android/data/**` → incluye `msgstore.db` de WhatsApp, es decir
  **el historial de chats no se puede copiar**. Solo su media.
- `/data/data/**` → datos privados de todas las apps.
- Contactos, SMS, registro de llamadas y ajustes.

> La app mostrará esto explícitamente en el asistente para que nadie crea
> que ha salvado sus conversaciones de WhatsApp cuando no es así. Para los
> chats, la vía es la copia de seguridad propia de WhatsApp o exportar chat.

---

## 4. Formato de salida

```
<carpeta elegida>/
└── bkp_02092026/                  ← bkp_DDMMYYYY (si ya existe: _2, _3…)
    ├── DCIM/…
    ├── Pictures/…
    ├── Download/…
    ├── WhatsApp/Media/…
    ├── RESUMEN.txt                ← informe legible
    └── manifiesto.json            ← qué se copió, tamaños, hashes, errores
```

Estructura de carpetas del móvil **replicada tal cual** dentro de la carpeta
de fecha, para que sea navegable sin la app.

---

## 5. Motor incremental

Índice en `~/.bkpmovil/index/<id_dispositivo>.json`:

```json
{
  "/sdcard/DCIM/Camera/IMG_0421.jpg": {
    "size": 3812044, "mtime": 1748100122, "bkp": "bkp_02092026"
  }
}
```

- Se considera **ya copiado** si coinciden ruta + tamaño + mtime.
- Se copia si es nuevo, si cambió el tamaño o si el mtime es posterior.
- Cada carpeta `bkp_DDMMYYYY` contiene **solo lo nuevo**; el manifiesto
  registra también qué se omitió y en qué copia anterior está.
- Opción "Forzar copia completa" para una copia autónoma puntual.
- El índice es reconstruible escaneando las copias anteriores (comando de
  reparación), para que perderlo no sea un desastre.

### Listado remoto
`adb shell "find <ruta> -type f -exec stat -c '%s|%Y|%n' {} +"`
(toybox de Android lo soporta). Fallback a `find -type f` sin metadatos y,
en última instancia, `ls -laR` parseado.

### Copia
`adb pull -a <origen> <destino>` fichero a fichero (o en lotes de N rutas,
que adb moderno acepta) para poder informar progreso real y saltar los ya
copiados. Verificación por tamaño tras cada fichero; opción de verificación
por `sha1sum` (más lenta, desactivada por defecto).

### Robustez
- Reintentos (3) por fichero ante corte de WiFi; si el dispositivo se cae,
  se pausa y se ofrece reconectar sin perder lo avanzado.
- Nombres de fichero inválidos en Windows (`: ? * " < > |`) → saneados y
  anotados en el manifiesto.
- Rutas largas en Windows → prefijo `\\?\`.
- Cancelación limpia: lo ya copiado queda válido y registrado.

---

## 6. Interfaz (PySide6)

```
┌─ BKPmovil ─────────────────────────────────────────────┐
│ [1 Conectar] [2 Carpetas] [3 Copiar] [4 Resumen]       │
├────────────────────────────────────────────────────────┤
│  Guía paso a paso con capturas del menú de Android     │
│                                                        │
│  IP        [192.168.1.50    ]                          │
│  Puerto    [41233           ]                          │
│  Código    [123456          ]  (solo la 1ª vez)        │
│                       [ Vincular ] [ Conectar ]        │
│  ● Conectado — Xiaomi Redmi Note 8 (Android 11)        │
│                                                        │
│  Destino   [/home/saavedra/Backups]  [ Examinar… ]     │
│                                                        │
│              [  HACER COPIA DE SEGURIDAD  ]            │
└────────────────────────────────────────────────────────┘
```

- **Pestaña 1 – Guía + conexión**: instrucciones paso a paso con imágenes,
  detección automática de la versión de Android para mostrar la rama
  correcta, y botón *Detectar móviles en la red* (escaneo mDNS `adb mdns
  services`, que en Android 11+ anuncia el servicio). Perfiles guardados.
- **Pestaña 2 – Carpetas**: checkboxes con las rutas detectadas realmente
  presentes en ese móvil + tamaño y nº de ficheros de cada una + botón
  *Añadir ruta personalizada*. Selector de carpeta destino con el
  explorador nativo del sistema (`QFileDialog`).
- **Pestaña 3 – Progreso**: barra global + barra por carpeta, fichero
  actual, velocidad, tiempo restante estimado, log desplegable, botones
  *Pausar* / *Cancelar*.
- **Pestaña 4 – Resumen** (requisito explícito): tabla final con
  **todas las carpetas copiadas** y **el número total de ficheros**:

```
Copia terminada: bkp_02092026            Duración: 24 min 11 s
Destino: /home/saavedra/Backups/bkp_02092026

Carpeta              Ficheros   Tamaño   Omitidos   Errores
DCIM                    4.812   12,4 GB      1.204        0
Pictures                1.033    3,1 GB          0        0
Download                  212    1,2 GB         18        1
WhatsApp/Media          6.740    9,8 GB      2.310        0
─────────────────────────────────────────────────────────
TOTAL                  12.797   26,5 GB      3.532        1

[ Abrir carpeta ]  [ Guardar informe ]  [ Ver errores ]
```

El mismo contenido se escribe en `RESUMEN.txt` dentro de la copia.

---

## 7. Arquitectura

```
src/bkpmovil/
├── adb.py          # wrapper: localizar binario, pair, connect, devices,
│                   # shell, pull, mdns. Sin lógica de negocio.
├── discovery.py    # detección de rutas presentes + tamaños
├── index.py        # índice incremental (carga, consulta, actualización)
├── backup.py       # motor: planifica, copia, reintenta, emite señales
├── report.py       # RESUMEN.txt + manifiesto.json
├── config.py       # perfiles de dispositivo, preferencias, rutas por defecto
├── paths.py        # catálogo de rutas conocidas de Android
└── ui/
    ├── main_window.py
    ├── page_connect.py
    ├── page_folders.py
    ├── page_progress.py
    └── page_report.py
```

Regla: **el núcleo (`adb`, `backup`, `index`) no importa Qt**. El motor corre
en un `QThread` y se comunica por señales, de modo que es testeable sin UI y
reutilizable desde una CLI (`python -m bkpmovil --profile movil-papa`).

---

## 8. Fases

| Fase | Contenido | Resultado |
|---|---|---|
| **0** | Repo, `pyproject.toml`, estructura, CI básica | Esqueleto ✔ |
| **1** | `adb.py` + `discovery.py` + CLI mínima que conecta y lista | Se puede conectar y ver qué hay |
| **2** | `index.py` + `backup.py` + `report.py` (CLI completa) | **Copia funcional por terminal** |
| **3** | UI PySide6: conexión, carpetas, progreso, resumen | App usable |
| **4** | Guía paso a paso con capturas, perfiles, autodetección mDNS | App para la familia |
| **5** | PyInstaller: AppImage + `.exe` con adb embebido | Distribuible |
| **6** | Extras: programar copias, verificación sha1, exportar informe PDF | Opcional |

La fase 2 ya cubre el 100% del requisito funcional; de la 3 en adelante es
usabilidad. Recomiendo parar a probar con tu móvil antiguo al acabar la 2.

---

## 9. Pruebas

- Unitarias del núcleo con un `adb` simulado (fixtures de salida real de
  `find`/`stat`/`pull`) — sin necesidad de móvil.
- Test de integración opcional marcado `@pytest.mark.device`, que solo corre
  si hay un dispositivo conectado.
- Casos cubiertos: nombres con espacios/emoji/acentos, ficheros de 0 bytes,
  ficheros >4 GB, corte de conexión a mitad, ruta inexistente, disco lleno,
  segunda ejecución el mismo día (sufijo `_2`), reanudación incremental.

---

## 10. Riesgos y mitigación

| Riesgo | Mitigación |
|---|---|
| El puerto ADB cambia cada vez | Siempre editable + botón de detección mDNS |
| El usuario confunde puerto de vinculación con el de conexión | Dos campos separados y explicados en la guía, con validación |
| Expectativa de "salvar WhatsApp" (chats) | Aviso explícito en la guía y en el resumen |
| WiFi lento o inestable en copias de decenas de GB | Reintentos, pausa/reanudar, incremental |
| Windows sin `adb` | adb embebido en el `.exe` |
| Móvil se bloquea y corta la sesión ADB | Aviso de "mantén la pantalla encendida" + reconexión automática |
