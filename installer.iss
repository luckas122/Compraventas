; Script de instalación para Tu local 2025
; Generado con Inno Setup 6
; Instala directamente en %LOCALAPPDATA%\Compraventas\app (sin admin)

#define MyAppName "Tu local 2025"
#define MyAppVersion "3.3.0"
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
Source: "dist\Tu local 2025\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.lnk,*.db"

[Tasks]
Name: "desktopicon"; Description: "Crear icono en el escritorio"; GroupDescription: "Iconos adicionales:"; Flags: checkedonce

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall

[Code]
var
  BackupDir: string;
  ConfigBackupPath: string;
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

function InitializeSetup(): Boolean;
var
  ConfigFile: string;
  PreviousInstallDir: string;
begin
  Result := True;
  ConfigFound := False;

  // Ruta temporal para backup de config
  BackupDir := ExpandConstant('{tmp}\TuLocal2025_ConfigBackup');
  ConfigBackupPath := BackupDir + '\app_config.json';

  Log('================================================');
  Log('INICIO DE INSTALACION - BACKUP DE CONFIGURACION');
  Log('================================================');

  // Buscar config en AppData (ubicacion actual desde v3.1+)
  ConfigFile := ExpandConstant('{userappdata}\CompraventasV2\app_config.json');
  Log('Buscando config en AppData: ' + ConfigFile);

  if FileExists(ConfigFile) then
  begin
    ConfigFound := True;
    Log('Config encontrado en AppData! Haciendo backup temporal...');
    if ForceDirectories(BackupDir) then
    begin
      if CopyFile(ConfigFile, ConfigBackupPath, False) then
        Log('>>> BACKUP EXITOSO: ' + ConfigBackupPath)
      else
        Log('>>> ERROR: No se pudo copiar el archivo');
    end else
      Log('>>> ERROR: No se pudo crear carpeta de backup');
  end
  else
  begin
    Log('Config no encontrado en AppData, buscando en instalacion anterior...');

    // FALLBACK: buscar en instalacion anterior (legacy Program Files)
    if RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{{#MyAppId}}_is1', 'InstallLocation', PreviousInstallDir) then
    begin
      if (Length(PreviousInstallDir) > 0) and (PreviousInstallDir[Length(PreviousInstallDir)] = '\') then
        PreviousInstallDir := Copy(PreviousInstallDir, 1, Length(PreviousInstallDir) - 1);
    end
    else if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{{#MyAppId}}_is1', 'InstallLocation', PreviousInstallDir) then
    begin
      if (Length(PreviousInstallDir) > 0) and (PreviousInstallDir[Length(PreviousInstallDir)] = '\') then
        PreviousInstallDir := Copy(PreviousInstallDir, 1, Length(PreviousInstallDir) - 1);
    end
    else
      PreviousInstallDir := '';

    if PreviousInstallDir <> '' then
    begin
      ConfigFile := PreviousInstallDir + '\_internal\app\app_config.json';
      Log('Buscando config legacy en: ' + ConfigFile);
      if FileExists(ConfigFile) then
      begin
        ConfigFound := True;
        Log('Config legacy encontrado! Haciendo backup...');
        if ForceDirectories(BackupDir) then
        begin
          if CopyFile(ConfigFile, ConfigBackupPath, False) then
            Log('>>> BACKUP EXITOSO: ' + ConfigBackupPath)
          else
            Log('>>> ERROR: No se pudo copiar el archivo');
        end else
          Log('>>> ERROR: No se pudo crear carpeta de backup');
      end else
        Log('Config no existe en instalacion previa');
    end else
      Log('No hay instalacion previa (instalacion limpia)');
  end;

  Log('================================================');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigDest: string;
  ConfigDir: string;
begin
  if CurStep = ssPostInstall then
  begin
    Log('================================================');
    Log('POST-INSTALACION - RESTAURAR CONFIGURACION');
    Log('================================================');

    // Restaurar config directo a AppData (donde la app la lee)
    if ConfigFound and FileExists(ConfigBackupPath) then
    begin
      ConfigDir := ExpandConstant('{userappdata}\CompraventasV2');
      ConfigDest := ConfigDir + '\app_config.json';
      Log('Restaurando config a: ' + ConfigDest);

      if ForceDirectories(ConfigDir) then
      begin
        if CopyFile(ConfigBackupPath, ConfigDest, False) then
        begin
          Log('>>> CONFIG RESTAURADA EXITOSAMENTE');
          DeleteFile(ConfigBackupPath);
        end else
          Log('>>> ERROR: No se pudo restaurar config');
      end else
        Log('>>> ERROR: No se pudo crear carpeta CompraventasV2');
    end else
      Log('No hay config para restaurar (instalacion limpia)');

    Log('================================================');
  end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := '';
  if MemoDirInfo <> '' then
    Result := Result + MemoDirInfo + NewLine + NewLine;

  if ConfigFound then
    Result := Result + 'Configuracion anterior:' + NewLine + Space + 'Se preservara automaticamente' + NewLine + NewLine
  else
    Result := Result + 'Configuracion anterior:' + NewLine + Space + 'No se encontro configuracion previa' + NewLine + NewLine;
end;
