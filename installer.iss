; Script de instalación para Tu local 2025
; Generado con Inno Setup 6

#define MyAppName "Tu local 2025"
#define MyAppVersion "3.0.0"
#define MyAppPublisher "Compraventas"
#define MyAppExeName "Tu local 2025.exe"
#define MyAppId "A1B2C3D4-E5F6-4789-ABCD-123456789ABC"

[Setup]
AppId={{{#MyAppId}}
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
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
DisableDirPage=no
UsePreviousAppDir=yes
SetupLogging=yes
AlwaysShowComponentsList=no
ShowLanguageDialog=no

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

[Files]
Source: "dist\Tu local 2025\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.lnk"

[Tasks]
Name: "backupconfig"; Description: "Restaurar configuración anterior (si existe)"; GroupDescription: "Opciones adicionales:"; Flags: checkedonce
Name: "desktopicon"; Description: "Crear icono en el escritorio"; GroupDescription: "Iconos adicionales:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall

[Code]
var
  BackupDir: string;
  ConfigBackupPath: string;
  PreviousInstallDir: string;
  ConfigFound: Boolean;

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

function GetPreviousInstallDir(): string;
var
  InstallDir: string;
begin
  Result := '';

  // Buscar en HKLM (instalación como admin)
  if RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{{#MyAppId}}_is1', 'InstallLocation', InstallDir) then
  begin
    // Quitar trailing backslash
    if (Length(InstallDir) > 0) and (InstallDir[Length(InstallDir)] = '\') then
      InstallDir := Copy(InstallDir, 1, Length(InstallDir) - 1);
    Result := InstallDir;
    Log('Instalación previa encontrada en HKLM: ' + Result);
    Exit;
  end;

  // Buscar en HKCU (instalación como usuario)
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{{#MyAppId}}_is1', 'InstallLocation', InstallDir) then
  begin
    if (Length(InstallDir) > 0) and (InstallDir[Length(InstallDir)] = '\') then
      InstallDir := Copy(InstallDir, 1, Length(InstallDir) - 1);
    Result := InstallDir;
    Log('Instalación previa encontrada en HKCU: ' + Result);
    Exit;
  end;

  Log('No se encontró instalación previa en el registro');
end;

function InitializeSetup(): Boolean;
var
  ConfigFile: string;
begin
  Result := True;
  ConfigFound := False;

  // Configurar rutas de backup (fuera de la carpeta de instalación)
  BackupDir := ExpandConstant('{userappdata}\Tu local 2025 Backup');
  ConfigBackupPath := BackupDir + '\app_config.json';

    Log('================================================');
  Log('INICIO DE INSTALACION - BACKUP DE CONFIGURACION');
  Log('================================================');

  // Obtener directorio de instalación previo desde el registro
  PreviousInstallDir := GetPreviousInstallDir();

  if PreviousInstallDir <> '' then
  begin
    ConfigFile := PreviousInstallDir + '\_internal\app\app_config.json';
    Log('Buscando config en: ' + ConfigFile);

    if FileExists(ConfigFile) then
    begin
      ConfigFound := True;
      Log('Config encontrado! Haciendo backup...');
      if ForceDirectories(BackupDir) then
      begin
        if FileCopy(ConfigFile, ConfigBackupPath, False) then
          Log('>>> BACKUP EXITOSO: ' + ConfigBackupPath)
        else
          Log('>>> ERROR: No se pudo copiar el archivo');
      end else
        Log('>>> ERROR: No se pudo crear carpeta de backup');
    end else
      Log('Config no existe en la instalación previa');
  end else
    Log('No hay instalación previa (instalación limpia)');

  Log('================================================');
end;

procedure InitializeWizard();
begin
  if ConfigFound then
  begin
    WizardSelectTasks('backupconfig');
    Log('Task backupconfig seleccionada automaticamente (config detectada)');
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  FinalBackupDir: string;
  FinalBackupPath: string;
begin
  if CurStep = ssPostInstall then
  begin
    FinalBackupDir := ExpandConstant('{app}\config_backup');
    FinalBackupPath := FinalBackupDir + '\app_config.json';

    Log('================================================');
    Log('POST-INSTALACION - MOVER BACKUP A CARPETA APP');
    Log('================================================');
    Log('Backup temporal en: ' + ConfigBackupPath);
    Log('Destino final: ' + FinalBackupPath);
    if IsTaskSelected('backupconfig') then
      Log('Task backupconfig seleccionada: SI')
    else
      Log('Task backupconfig seleccionada: NO');

    // Siempre mover el backup si existe; la app preguntara si restaurar
    if FileExists(ConfigBackupPath) then
    begin
      Log('Backup encontrado, moviendo a carpeta de la app...');
      if ForceDirectories(FinalBackupDir) then
      begin
        if FileCopy(ConfigBackupPath, FinalBackupPath, False) then
        begin
          Log('>>> BACKUP MOVIDO EXITOSAMENTE');
          Log('>>> Ubicacion: ' + FinalBackupPath);
          DeleteFile(ConfigBackupPath);
          RemoveDir(BackupDir);
        end else
          Log('>>> ERROR: No se pudo mover backup');
      end else
        Log('>>> ERROR: No se pudo crear carpeta config_backup');
    end else
      Log('No hay backup para mover (instalacion limpia o config no encontrado)');
    Log('================================================');
    Log('La aplicación se abrirá y preguntará si restaurar');
    Log('================================================');
  end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := '';
  if MemoDirInfo <> '' then
    Result := Result + MemoDirInfo + NewLine + NewLine;

  if ConfigFound then
  begin
    if IsTaskSelected('backupconfig') then
      Result := Result + 'Configuración anterior:' + NewLine + Space + 'Se restaurará después de la instalación' + NewLine + NewLine
    else
      Result := Result + 'Configuración anterior:' + NewLine + Space + 'NO se restaurará (se usará configuración limpia)' + NewLine + NewLine;
  end else
    Result := Result + 'Configuración anterior:' + NewLine + Space + 'No se encontró configuración previa' + NewLine + NewLine;
end;
