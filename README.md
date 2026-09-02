# BKPmovil

Copia de seguridad de un móvil Android al ordenador **por WiFi**, sin cables
y sin root, usando la *depuración inalámbrica* de Android.

Pensada para gente no técnica: se elige la marca del móvil, se siguen cuatro
pasos con la guía que trae la propia aplicación, se pulsa un botón y listo.
La primera copia lo trae todo; a partir de ahí **solo trae lo nuevo**.

![Elegir carpetas](docs/capturas/2-carpetas.png)

## Qué hace

- **Copia por WiFi**, sin cable y sin rootear el móvil.
- **Incremental**: la segunda copia tarda minutos en vez de horas.
- Detecta solas las carpetas habituales — cámara, imágenes, vídeos,
  descargas, documentos, capturas, grabaciones, música, Bluetooth — y deja
  **añadir o quitar las que quieras**.
- Busca por todo el móvil las carpetas de **WhatsApp, Telegram y Signal** y
  copia de ellas **las fotos y vídeos que no están en la carpeta de la
  cámara**.
- Elige el destino con el **explorador de archivos** del sistema y crea sola
  una carpeta `bkp_DDMMYYYY` con la fecha del día.
- **Guía paso a paso** con la ruta exacta del menú de cada marca: Samsung,
  Google Pixel, Xiaomi/Redmi/POCO, Huawei/Honor, OPPO/realme/OnePlus y
  Android genérico, más el modo por cable para Android 10 o anterior.
- **Progreso en vivo**: carpeta y fichero en curso, ficheros copiados,
  velocidad y tiempo restante. Se puede pausar y cancelar sin perder nada.
- **Resumen final** con las carpetas copiadas y el número total de ficheros,
  guardado también como `RESUMEN.txt` y `manifiesto.json` dentro de la copia.
- Aguanta cortes de WiFi: reintenta y se reconecta solo.
- Funciona igual desde la **terminal**, para automatizar copias.

## Instalación

Descarga la última versión desde la
**[página de versiones](https://github.com/fergballes/BKPmovil/releases/latest)**.
Los paquetes llevan `adb` dentro: no hace falta instalar nada más.

**Windows** — abre `BKPmovil-X.Y.Z-instalador.exe` y deja marcada la casilla
del acceso directo en el Escritorio. Windows avisará de que la aplicación no
está firmada: *Más información* → *Ejecutar de todas formas*. También hay un
`.zip` portable.

**Linux** — descomprime el `.tar.gz` y ejecuta `./instalar.sh` dentro de la
carpeta. Queda en el menú de aplicaciones y con acceso directo en el
Escritorio.

📖 **[Guía completa de uso](docs/GUIA.md)** — instalación, conexión paso a
paso por marca, resolución de problemas y uso desde la terminal.

## Los dos puertos

Es el error más común, así que conviene saberlo de antemano: en Android 11 o
superior, el puerto de **vinculación** (el de la ventana emergente con el
código de 6 cifras) y el de **conexión** (el de la pantalla principal de
*Depuración inalámbrica*) **son distintos**. Además, el de conexión cambia
cada vez que reinicias el móvil o el WiFi. La vinculación solo se hace una
vez por ordenador.

## Qué no se puede copiar

Sin acceso de superusuario, Android bloquea `/sdcard/Android/data`. Por eso
**el historial de chats de WhatsApp no se puede copiar** con esta ni con
ninguna herramienta parecida; sus fotos, vídeos y audios sí. Para los chats,
usa la copia de seguridad del propio WhatsApp.

Tampoco se copian contactos, SMS ni los datos internos de las aplicaciones.

## Uso desde la terminal

```bash
bkpmovil pair    --host 192.168.1.50 --port 37451 --code 123456   # solo la 1ª vez
bkpmovil connect --host 192.168.1.50 --port 41233
bkpmovil backup  --dest "~/Copias BKPmovil" --open
```

`bkpmovil --help` lista el resto: `devices`, `list`, `tcpip`,
`rebuild-index`, y las opciones `--only`, `--full` y `--verify`.

## Desarrollo

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                      # 74 pruebas, con un móvil simulado (no hace falta uno real)
ruff check src tests tools
python -m bkpmovil           # abre la ventana
python tools/build.py        # genera el paquete distribuible en dist/
```

### Cómo está organizado

```
src/bkpmovil/
├── adb.py          envoltorio del ejecutable adb (pair, connect, shell, pull)
├── paths.py        catálogo de rutas de Android y filtros por extensión
├── discovery.py    qué carpetas existen en este móvil y qué contienen
├── index.py        índice incremental: qué se copió ya y en qué copia
├── backup.py       motor de copia: planifica, copia, reintenta, informa
├── report.py       RESUMEN.txt y manifiesto.json
├── config.py       preferencias y perfiles de dispositivo
├── guide.py        guía de conexión, por fabricante
├── cli.py          línea de órdenes
└── ui/             interfaz PySide6, un módulo por paso
```

El núcleo no importa Qt: se puede usar y probar sin interfaz. El motor corre
en un hilo aparte y se comunica con la ventana por señales.

Las pruebas levantan un **móvil simulado** sobre una carpeta temporal y
ejecutan contra ella las mismas órdenes (`find`, `stat`) que se enviarían a
un Android real, así que se valida el texto exacto que se manda y su parseo.

## Requisitos para ejecutar desde el código

- Python 3.11 o superior
- `adb` — en Arch, `sudo pacman -S android-tools`

## Licencia

MIT
