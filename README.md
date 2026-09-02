# BKPmovil

Copia de seguridad de un móvil Android al ordenador **por WiFi**, sin cables
y sin root, usando la *depuración inalámbrica* de Android y `adb`.

Pensada para uso personal y familiar: se introduce la IP, el puerto y el
código de vinculación, se elige la carpeta de destino y un botón hace el
resto. Al terminar muestra todas las carpetas copiadas y el número total de
ficheros.

## Estado

En desarrollo. Ver [PLAN.md](PLAN.md) para el diseño completo y las fases.

## Características previstas

- Guía paso a paso para activar la depuración inalámbrica en el móvil.
- Conexión por IP + puerto + código de 6 dígitos (Android 11+) o `tcpip 5555`.
- Selección de carpetas a copiar, detectadas automáticamente con su tamaño.
- Selector de carpeta de destino con el explorador de archivos del sistema.
- Copia **incremental**: solo lo nuevo desde la última vez.
- Salida en `bkp_DDMMYYYY/` con la estructura del móvil replicada.
- Informe final con carpetas copiadas, ficheros, tamaños y errores.

## Requisitos

- Python 3.11+
- `adb` (paquete `android-tools` en Arch). En los ejecutables empaquetados
  va incluido.

## Desarrollo

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Limitaciones

Sin root, Android no permite leer `/sdcard/Android/data/**`, por lo que
**el historial de chats de WhatsApp no se puede copiar** (sí sus fotos,
vídeos y audios). Tampoco contactos, SMS ni datos internos de apps.

## Licencia

MIT
