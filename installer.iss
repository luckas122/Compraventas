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
; Permitir instalación en Program Files (requiere admin)
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
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
  DBFile: string;
  ConfigBackup: string;
  DBBackup: string;
  ConfigDir: string;
begin
  // ANTES de instalar: respaldar config y BD si existen
  if CurStep = ssInstall then
  begin
    ConfigFile := ExpandConstant('{app}\_internal\app\app_config.json');
    DBFile := ExpandConstant('{app}\appcomprasventas.db');
    ConfigBackup := ExpandConstant('{tmp}\app_config_backup.json');
    DBBackup := ExpandConstant('{tmp}\db_backup.db');

    Log('=== RESPALDO PRE-INSTALACIÓN ===');
    Log('Buscando config en: ' + ConfigFile);
    Log('Buscando BD en: ' + DBFile);

    if FileExists(ConfigFile) then
    begin
      Log('✓ Config encontrado, respaldando...');
      if FileCopy(ConfigFile, ConfigBackup, False) then
        Log('✓ Config respaldado exitosamente')
      else
        Log('✗ ERROR: No se pudo respaldar config');
    end else
      Log('- Config no existe (instalación limpia)');

    if FileExists(DBFile) then
    begin
      Log('✓ BD encontrada, respaldando...');
      if FileCopy(DBFile, DBBackup, False) then
        Log('✓ BD respaldada exitosamente')
      else
        Log('✗ ERROR: No se pudo respaldar BD');
    end else
      Log('- BD no existe (instalación limpia)');
  end;

  // DESPUÉS de instalar: restaurar config y BD
  if CurStep = ssPostInstall then
  begin
    ConfigFile := ExpandConstant('{app}\_internal\app\app_config.json');
    DBFile := ExpandConstant('{app}\appcomprasventas.db');
    ConfigBackup := ExpandConstant('{tmp}\app_config_backup.json');
    DBBackup := ExpandConstant('{tmp}\db_backup.db');
    ConfigDir := ExpandConstant('{app}\_internal\app');

    Log('=== RESTAURACIÓN POST-INSTALACIÓN ===');
    Log('Verificando backups...');
    Log('ConfigBackup existe: ' + IntToStr(Integer(FileExists(ConfigBackup))));
    Log('DBBackup existe: ' + IntToStr(Integer(FileExists(DBBackup))));

    // Asegurar que existe la carpeta _internal\app
    if not DirExists(ConfigDir) then
    begin
      Log('Creando carpeta: ' + ConfigDir);
      if ForceDirectories(ConfigDir) then
        Log('✓ Carpeta creada')
      else
        Log('✗ ERROR: No se pudo crear carpeta');
    end;

    if FileExists(ConfigBackup) then
    begin
      Log('Restaurando config a: ' + ConfigFile);
      if FileCopy(ConfigBackup, ConfigFile, False) then
      begin
        Log('✓ Config restaurado exitosamente');
        DeleteFile(ConfigBackup);
      end else
        Log('✗ ERROR: No se pudo restaurar config');
    end else
      Log('- No hay config para restaurar');

    if FileExists(DBBackup) then
    begin
      Log('Restaurando BD a: ' + DBFile);
      if FileCopy(DBBackup, DBFile, False) then
      begin
        Log('✓ BD restaurada exitosamente');
        DeleteFile(DBBackup);
      end else
        Log('✗ ERROR: No se pudo restaurar BD');
    end else
      Log('- No hay BD para restaurar');

    Log('=== FIN RESTAURACIÓN ===');
  end;
end;
