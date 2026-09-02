#!/usr/bin/env bash
# Instala BKPmovil para el usuario actual y crea el acceso directo.
set -euo pipefail

ORIGEN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINO="${HOME}/.local/opt/BKPmovil"
APPS="${HOME}/.local/share/applications"
ICONOS="${HOME}/.local/share/icons/hicolor"

echo "Instalando BKPmovil en ${DESTINO}…"
rm -rf "${DESTINO}"
mkdir -p "${DESTINO}" "${APPS}"
cp -r "${ORIGEN}/." "${DESTINO}/"
chmod +x "${DESTINO}/BKPmovil"
[ -f "${DESTINO}/_internal/vendor/adb" ] && chmod +x "${DESTINO}/_internal/vendor/adb" || true

for TAM in 16 24 32 48 64 128 256; do
  ORIGEN_ICONO="${DESTINO}/_internal/assets/icono-${TAM}.png"
  if [ -f "${ORIGEN_ICONO}" ]; then
    mkdir -p "${ICONOS}/${TAM}x${TAM}/apps"
    cp "${ORIGEN_ICONO}" "${ICONOS}/${TAM}x${TAM}/apps/bkpmovil.png"
  fi
done

sed "s|BKPMOVIL_EXEC|${DESTINO}/BKPmovil|" "${DESTINO}/bkpmovil.desktop" \
  > "${APPS}/bkpmovil.desktop"
chmod +x "${APPS}/bkpmovil.desktop"

command -v update-desktop-database >/dev/null && update-desktop-database "${APPS}" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -f -t "${ICONOS}" 2>/dev/null || true

if [ -d "${HOME}/Escritorio" ]; then ESCRITORIO="${HOME}/Escritorio";
elif [ -d "${HOME}/Desktop" ]; then ESCRITORIO="${HOME}/Desktop"; else ESCRITORIO=""; fi
if [ -n "${ESCRITORIO}" ]; then
  cp "${APPS}/bkpmovil.desktop" "${ESCRITORIO}/bkpmovil.desktop"
  chmod +x "${ESCRITORIO}/bkpmovil.desktop"
  echo "Acceso directo creado en ${ESCRITORIO}"
fi

echo
echo "Listo. Busca «BKPmovil» en el menú de aplicaciones."
echo "Para desinstalar:  rm -rf '${DESTINO}' '${APPS}/bkpmovil.desktop'"
