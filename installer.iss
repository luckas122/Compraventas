; Script de instalación para Tu local 2025
; Generado con Inno Setup 6
; Instala directamente en %LOCALAPPDATA%\Compraventas\app (sin admin)
; Config vive en %APPDATA%\CompraventasV2\ y NO se toca durante instalacion

#define MyAppName "Tu local 2025"
#define MyAppVersion "3.5.0"
#define MyAppPublisher "Compraventas"
#define MyAppExeName "Tu local 2025.exe"
#define MyAppId "A1B2C3D4-E5F6-4789-ABCD-123456789ABC"

[Setup]
AppId={{{#MyAppId}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Compraventas\app
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=Tu.local.2025.v{#MyAppVersion}.Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64
DisableDirPage=yes
UsePreviousAppDir=yes
SetupLogging=yes
AlwaysShowComponentsList=no
ShowLanguageDialog=no

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

[Files]
; Instala archivos de app. Excluye DB (la app la crea) y accesos directos sueltos
Source: "dist\Tu local 2025\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.lnk,*.db"

[Tasks]
Name: "desktopicon"; Description: "Crear icono en el escritorio"; GroupDescription: "Iconos adicionales:"; Flags: checkedonce

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall

; Sin [Code] - El instalador simplemente instala archivos.
; La configuracion vive en %APPDATA%\CompraventasV2\ (carpeta separada)
; y NO se toca durante la instalacion/actualizacion.
; Si el usuario necesita restaurar config, la app lo pregunta al iniciar.
