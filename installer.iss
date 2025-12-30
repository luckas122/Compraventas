; Script de instalación para Tu local 2025
; Generado con Inno Setup 6

#define MyAppName "Tu local 2025"
#define MyAppVersion "2.8.5"
#define MyAppPublisher "Compraventas"
#define MyAppExeName "Tu local 2025.exe"

[Setup]
; Información básica
AppId={{A1B2C3D4-E5F6-4789-ABCD-123456789ABC}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=Tu.local.2025.v{#MyAppVersion}.Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
; Permitir que el usuario elija la ruta de instalación
DisableDirPage=no
UsePreviousAppDir=yes

; Accesos directos
[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

; Archivos a instalar
[Files]
; Copiar TODOS los archivos de la carpeta dist recursivamente
Source: "dist\Tu local 2025\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Ejecutar app después de instalar
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

; Código para preservar config y BD en actualizaciones
[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigFile: string;
  DBFile: string;
  ConfigBackup: string;
  DBBackup: string;
begin
  // ANTES de instalar: respaldar config y BD si existen
  if CurStep = ssInstall then
  begin
    // Ahora sí podemos usar {app} porque ya se definió la ruta de instalación
    ConfigFile := ExpandConstant('{app}\_internal\app\app_config.json');
    DBFile := ExpandConstant('{app}\appcomprasventas.db');
    ConfigBackup := ExpandConstant('{tmp}\app_config_backup.json');
    DBBackup := ExpandConstant('{tmp}\db_backup.db');

    if FileExists(ConfigFile) then
    begin
      Log('Respaldando configuración desde: ' + ConfigFile);
      FileCopy(ConfigFile, ConfigBackup, False);
    end;

    if FileExists(DBFile) then
    begin
      Log('Respaldando base de datos desde: ' + DBFile);
      FileCopy(DBFile, DBBackup, False);
    end;
  end;

  // DESPUÉS de instalar: restaurar config y BD
  if CurStep = ssPostInstall then
  begin
    ConfigFile := ExpandConstant('{app}\_internal\app\app_config.json');
    DBFile := ExpandConstant('{app}\appcomprasventas.db');
    ConfigBackup := ExpandConstant('{tmp}\app_config_backup.json');
    DBBackup := ExpandConstant('{tmp}\db_backup.db');

    if FileExists(ConfigBackup) then
    begin
      Log('Restaurando configuración a: ' + ConfigFile);
      FileCopy(ConfigBackup, ConfigFile, False);
      DeleteFile(ConfigBackup);
    end;

    if FileExists(DBBackup) then
    begin
      Log('Restaurando base de datos a: ' + DBFile);
      FileCopy(DBBackup, DBFile, False);
      DeleteFile(DBBackup);
    end;
  end;
end;
