; Script de instalación para Tu local 2025
; Generado con Inno Setup 6

#define MyAppName "Tu local 2025"
#define MyAppVersion "3.0.0"
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
; Permitir instalación en Program Files (requiere admin)
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
; Permitir que el usuario elija la ruta de instalación
DisableDirPage=no
UsePreviousAppDir=yes
; Configuración de logs y actualizaciones
SetupLogging=yes
AlwaysShowComponentsList=no
ShowLanguageDialog=no

; Accesos directos
[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

; Archivos a instalar
[Files]
; Copiar TODOS los archivos de la carpeta dist recursivamente
Source: "dist\Tu local 2025\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Ejecutar app después de instalar (sin skipifsilent para que siempre abra)
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall

; Código para preservar config en actualizaciones
; NUEVO ENFOQUE: Solo hacer backup, la app preguntará si restaurar
[Code]
function ForceDirectories(Dir: string): Boolean;
var
  Parent: string;
begin
  Result := DirExists(Dir);
  if Result then Exit;

  Parent := ExtractFileDir(Dir);
  if (Parent <> '') and (Parent <> Dir) then
  begin
    Result := ForceDirectories(Parent);
    if Result then
      Result := CreateDir(Dir);
  end else
    Result := CreateDir(Dir);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigFile: string;
  BackupDir: string;
  ConfigBackup: string;
begin
  // ANTES de instalar: respaldar config si existe
  if CurStep = ssInstall then
  begin
    // Backup DENTRO de la carpeta de la app (sobrevive a la instalación)
    BackupDir := ExpandConstant('{app}\config_backup');
    ConfigFile := ExpandConstant('{app}\_internal\app\app_config.json');
    ConfigBackup := BackupDir + '\app_config.json';

    Log('=== RESPALDO PRE-INSTALACION ===');
    Log('Directorio de backup: ' + BackupDir);
    Log('Buscando config en: ' + ConfigFile);

    if FileExists(ConfigFile) then
    begin
      Log('Config encontrado, creando carpeta backup...');
      if ForceDirectories(BackupDir) then
      begin
        Log('Carpeta backup creada: ' + BackupDir);
        if FileCopy(ConfigFile, ConfigBackup, False) then
          Log('Config respaldado exitosamente a: ' + ConfigBackup)
        else
          Log('ERROR: No se pudo respaldar config');
      end else
        Log('ERROR: No se pudo crear carpeta backup');
    end else
      Log('Config no existe (instalacion limpia, no hay backup que hacer)');
  end;

  // DESPUES de instalar: NO restauramos automáticamente
  // La app detectará el backup y preguntará al usuario
  if CurStep = ssPostInstall then
  begin
    BackupDir := ExpandConstant('{app}\config_backup');
    ConfigBackup := BackupDir + '\app_config.json';

    Log('=== POST-INSTALACION ===');
    if FileExists(ConfigBackup) then
      Log('Backup de config existe en: ' + ConfigBackup + ' - La app preguntara al usuario si restaurar')
    else
      Log('No hay backup de config (instalacion limpia)');

    Log('La aplicacion se abrira y manejara la restauracion');
  end;
end;
