"""Guía de conexión paso a paso, adaptada a cada fabricante.

El menú de Android cambia bastante entre marcas, y es donde se atasca la
gente. Aquí está la ruta exacta de cada una.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Guide:
    key: str
    label: str
    developer_steps: list[str]
    wireless_steps: list[str]
    notes: list[str] = field(default_factory=list)


GENERIC_WIRELESS = [
    "Entra en <b>Opciones de desarrollador</b> y activa <b>Depuración inalámbrica</b>.",
    "Toca sobre el texto <b>Depuración inalámbrica</b> (no sobre el interruptor) "
    "para abrir su pantalla.",
    "Pulsa <b>Vincular dispositivo con un código de vinculación</b>.",
    "Aparecerá una ventana con un <b>código de 6 cifras</b> y una línea "
    "<b>IP:puerto</b>. Copia esos datos en el paso 2 de esta app y pulsa "
    "<b>Vincular</b>. <b>No cierres esa ventana del móvil</b> hasta que la app "
    "diga que ha funcionado.",
    "Cuando esté vinculado, mira la <b>IP y el puerto</b> que aparecen en la "
    "pantalla principal de Depuración inalámbrica: <b>son distintos</b> de los "
    "de la ventana anterior. Cópialos en la app y pulsa <b>Conectar</b>.",
]

GUIDES: tuple[Guide, ...] = (
    Guide(
        key="generico",
        label="Android genérico (Android 11 o superior)",
        developer_steps=[
            "Abre <b>Ajustes</b>.",
            "Entra en <b>Acerca del teléfono</b>.",
            "Pulsa <b>7 veces seguidas</b> sobre <b>Número de compilación</b>.",
            "Te pedirá el PIN y dirá «Ya eres desarrollador».",
            "Vuelve atrás y busca <b>Opciones de desarrollador</b> "
            "(suele estar dentro de <b>Sistema</b>).",
        ],
        wireless_steps=GENERIC_WIRELESS,
    ),
    Guide(
        key="samsung",
        label="Samsung (Galaxy · One UI)",
        developer_steps=[
            "Abre <b>Ajustes</b>.",
            "Baja del todo y entra en <b>Acerca del teléfono</b>.",
            "Entra en <b>Información del software</b>.",
            "Pulsa <b>7 veces seguidas</b> sobre <b>Número de compilación</b>.",
            "Introduce tu PIN. Verás «El modo de desarrollador está activado».",
            "Vuelve a <b>Ajustes</b> y entra en <b>Opciones de desarrollador</b> "
            "(al final de la lista).",
        ],
        wireless_steps=GENERIC_WIRELESS,
        notes=[
            "En algunos Galaxy la opción se llama <b>Depuración inalámbrica</b> "
            "y está justo debajo de <b>Depuración USB</b>.",
        ],
    ),
    Guide(
        key="google",
        label="Google Pixel (Android puro)",
        developer_steps=[
            "Abre <b>Ajustes</b>.",
            "Entra en <b>Información del teléfono</b>.",
            "Pulsa <b>7 veces seguidas</b> sobre <b>Número de compilación</b>.",
            "Introduce tu PIN.",
            "Vuelve a <b>Ajustes</b> → <b>Sistema</b> → "
            "<b>Opciones para desarrolladores</b>.",
        ],
        wireless_steps=GENERIC_WIRELESS,
    ),
    Guide(
        key="xiaomi",
        label="Xiaomi · Redmi · POCO (MIUI / HyperOS)",
        developer_steps=[
            "Abre <b>Ajustes</b>.",
            "Entra en <b>Sobre el teléfono</b>.",
            "Pulsa <b>7 veces seguidas</b> sobre <b>Versión de HyperOS</b> "
            "(o <b>Versión de MIUI</b> en móviles más antiguos).",
            "Verás «Ya eres desarrollador».",
            "Vuelve a <b>Ajustes</b> → <b>Ajustes adicionales</b> → "
            "<b>Opciones de desarrollador</b>.",
        ],
        wireless_steps=GENERIC_WIRELESS,
        notes=[
            "Xiaomi pide a veces iniciar sesión con la <b>cuenta Mi</b> y tener "
            "una SIM puesta para activar la depuración. Si te lo pide, hazlo: "
            "es un requisito del móvil, no de esta app.",
            "Activa también <b>Depuración USB</b> si la depuración inalámbrica "
            "aparece en gris.",
        ],
    ),
    Guide(
        key="huawei",
        label="Huawei · Honor (EMUI / MagicOS)",
        developer_steps=[
            "Abre <b>Ajustes</b>.",
            "Entra en <b>Acerca del teléfono</b>.",
            "Pulsa <b>7 veces seguidas</b> sobre <b>Número de compilación</b>.",
            "Vuelve a <b>Ajustes</b> → <b>Sistema y actualizaciones</b> → "
            "<b>Opciones de desarrollador</b>.",
        ],
        wireless_steps=GENERIC_WIRELESS,
    ),
    Guide(
        key="oppo",
        label="OPPO · realme · OnePlus (ColorOS)",
        developer_steps=[
            "Abre <b>Ajustes</b>.",
            "Entra en <b>Acerca del dispositivo</b>.",
            "Entra en <b>Versión</b> (en algunos modelos hace falta este paso).",
            "Pulsa <b>7 veces seguidas</b> sobre <b>Número de compilación</b>.",
            "Vuelve a <b>Ajustes</b> → <b>Ajustes adicionales</b> → "
            "<b>Opciones de desarrollador</b>.",
        ],
        wireless_steps=GENERIC_WIRELESS,
    ),
)

GUIDES_BY_KEY = {g.key: g for g in GUIDES}


#: Para Android 10 o anterior no existe la vinculación con código.
LEGACY_GUIDE = Guide(
    key="legacy",
    label="Android 10 o anterior (hace falta el cable una vez)",
    developer_steps=[
        "Activa las <b>Opciones de desarrollador</b> igual que en tu marca "
        "(pulsando 7 veces en el número de compilación).",
        "Dentro, activa <b>Depuración USB</b>.",
    ],
    wireless_steps=[
        "Conecta el móvil al ordenador <b>con el cable USB</b>.",
        "En el móvil, acepta el aviso <b>«¿Permitir depuración USB?»</b> y marca "
        "<b>Permitir siempre desde este ordenador</b>.",
        "En esta app, pulsa <b>Activar por cable (Android 10 o anterior)</b>.",
        "Cuando lo diga la app, <b>desconecta el cable</b>: a partir de ahí ya "
        "va por WiFi.",
    ],
    notes=[
        "Este modo se desactiva al reiniciar el móvil; habría que repetirlo "
        "con el cable.",
    ],
)

ANTES_DE_EMPEZAR = [
    "El móvil y el ordenador deben estar en <b>la misma red WiFi</b> "
    "(el mismo router; no vale que uno vaya por datos móviles).",
    "Ten el móvil <b>desbloqueado</b> y con la pantalla encendida durante la copia.",
    "Si puedes, enchufa el móvil al cargador: una copia grande tarda un rato.",
]

QUE_SE_COPIA = [
    "Fotos y vídeos de la cámara, capturas de pantalla, descargas y documentos.",
    "Las <b>fotos y vídeos de WhatsApp, Telegram y Signal</b>, que están en sus "
    "propias carpetas y no en la de la cámara.",
    "Puedes añadir cualquier otra carpeta del móvil tú mismo.",
]

QUE_NO_SE_COPIA = [
    "El <b>historial de chats</b> de WhatsApp: Android lo guarda en una zona "
    "protegida a la que ninguna aplicación de este tipo puede acceder sin "
    "«rootear» el móvil. Para eso, usa la copia de seguridad del propio "
    "WhatsApp.",
    "Contactos, SMS y registro de llamadas (se sincronizan con tu cuenta de Google).",
    "Los datos internos del resto de aplicaciones.",
]


def guide_for(manufacturer: str) -> Guide:
    """Elige la guía que corresponde a un fabricante detectado por adb."""
    low = (manufacturer or "").lower()
    mapping = {
        "samsung": "samsung",
        "google": "google",
        "xiaomi": "xiaomi",
        "redmi": "xiaomi",
        "poco": "xiaomi",
        "huawei": "huawei",
        "honor": "huawei",
        "oppo": "oppo",
        "realme": "oppo",
        "oneplus": "oppo",
    }
    for token, key in mapping.items():
        if token in low:
            return GUIDES_BY_KEY[key]
    return GUIDES_BY_KEY["generico"]
