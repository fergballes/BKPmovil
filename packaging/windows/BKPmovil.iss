; Instalador de BKPmovil para Windows (Inno Setup 6).
; Se compila con:  iscc packaging\windows\BKPmovil.iss
#define MiNombre "BKPmovil"
#ifndef MiVersion
  #define MiVersion "0.1.0"
#endif

[Setup]
AppId={{8F3A6C24-4C4B-4C1E-9C7E-BKPMOVIL0001}
AppName={#MiNombre}
AppVersion={#MiVersion}
AppPublisher=BKPmovil
DefaultDirName={autopf}\{#MiNombre}
DefaultGroupName={#MiNombre}
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=BKPmovil-{#MiVersion}-instalador
SetupIconFile=..\..\assets\icono.ico
UninstallDisplayIcon={app}\BKPmovil.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el Escritorio"; \
  GroupDescription: "Accesos directos:"

[Files]
Source: "..\..\dist\BKPmovil\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MiNombre}"; Filename: "{app}\BKPmovil.exe"
Name: "{autodesktop}\{#MiNombre}"; Filename: "{app}\BKPmovil.exe"; Tasks: escritorio

[Run]
Filename: "{app}\BKPmovil.exe"; Description: "Abrir BKPmovil"; \
  Flags: nowait postinstall skipifsilent
