; Inno Setup script for the Windows app.  iscc /DAppVersion=2.0.0 windows\installer.iss
; Installs for the current user only (no admin rights needed). Data lives in %APPDATA%\PixxelSpool; on uninstall
; the user is asked whether to delete it too (default: keep it).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef NumVersion
  #define NumVersion "0.0.0.0"
#endif

[Setup]
AppId={{7C1E5A52-3E0B-4B57-9C55-5F2B1D6A9E31}
AppName=PixxelSpool
AppVersion={#AppVersion}
AppVerName=PixxelSpool {#AppVersion}
UninstallDisplayName=PixxelSpool
AppCopyright=pixxelhoff
VersionInfoCompany=pixxelhoff
VersionInfoVersion={#NumVersion}
VersionInfoTextVersion={#AppVersion}
VersionInfoDescription=PixxelSpool Setup
VersionInfoProductName=PixxelSpool
AppPublisher=pixxelhoff
AppPublisherURL=https://github.com/pixxelhoff
DefaultDirName={localappdata}\Programs\PixxelSpool
DefaultGroupName=PixxelSpool
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=PixxelSpool-Setup-{#AppVersion}
SetupIconFile=pixxelspool-setup.ico
UninstallDisplayIcon={app}\PixxelSpool.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
LicenseFile=..\LICENSE

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
de.Autostart=PixxelSpool mit Windows starten
en.Autostart=Start PixxelSpool with Windows
es.Autostart=Iniciar PixxelSpool con Windows
de.Launch=PixxelSpool jetzt starten
en.Launch=Start PixxelSpool now
es.Launch=Iniciar PixxelSpool ahora
de.DeleteData=Sollen auch alle Daten von PixxelSpool gelöscht werden?%n%nDazu gehören die Datenbank mit allen Rollen, Einstellungen, Sicherungen und Protokolle in:%n%1%n%nDas lässt sich nicht rückgängig machen. Wähle „Nein“, wenn du PixxelSpool später wieder installieren und deine Daten behalten möchtest.
en.DeleteData=Also delete all PixxelSpool data?%n%nThis includes the database with all spools, settings, backups and logs in:%n%1%n%nThis cannot be undone. Choose “No” if you want to reinstall PixxelSpool later and keep your data.
es.DeleteData=¿Borrar también todos los datos de PixxelSpool?%n%nIncluye la base de datos con todas las bobinas, los ajustes, las copias de seguridad y los registros en:%n%1%n%nNo se puede deshacer. Elige «No» si quieres reinstalar PixxelSpool más adelante y conservar tus datos.

[Tasks]
Name: "autostart"; Description: "{cm:Autostart}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"

[Files]
Source: "..\dist\PixxelSpool\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PixxelSpool"; Filename: "{app}\PixxelSpool.exe"
Name: "{autodesktop}\PixxelSpool"; Filename: "{app}\PixxelSpool.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "PixxelSpool"; \
  ValueData: """{app}\PixxelSpool.exe"" --no-browser"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\PixxelSpool.exe"; Description: "{cm:Launch}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/IM PixxelSpool.exe /F"; Flags: runhidden; RunOnceId: "StopApp"
; close the app window (Edge/Chrome started with PixxelSpool's own profile), so its files can be deleted
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Get-CimInstance Win32_Process | Where-Object {{ $_.Name -match 'msedge|chrome' -and $_.CommandLine -like '*PixxelSpool\window*' } | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }"""; Flags: runhidden; RunOnceId: "StopWindow"

[UninstallDelete]
; anything created next to the program after installing
Type: filesandordirs; Name: "{app}"

[Code]
// After the program files are gone: remove the autostart entry (it may have been switched on in the tray menu)
// and, if the user agrees, the data folder (database, settings, backups, logs, app window profile).
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'PixxelSpool');
    DataDir := ExpandConstant('{userappdata}\PixxelSpool');
    if DirExists(DataDir) and not UninstallSilent then
      if MsgBox(FmtMessage(CustomMessage('DeleteData'), [DataDir]), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
