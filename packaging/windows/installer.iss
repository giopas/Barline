; Inno Setup script for SSP - Song and Setlist Planner (Windows).
; Build:  ISCC /DAppVersion=0.10.0 packaging\windows\installer.iss   (after pyinstaller)
; Per-user install: no administrator needed. Songs are not in the program
; folder (they live in %APPDATA%\SingleSongPlanner), so uninstalling or
; updating never touches them.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{68A4579C-2AED-4FD0-AE62-3A4F81AF74D4}
AppName=SSP - Song and Setlist Planner
AppVersion={#AppVersion}
AppPublisher=giopas
AppPublisherURL=https://github.com/giopas/SSP---Song-and-Setlist-Planner
AppSupportURL=https://github.com/giopas/SSP---Song-and-Setlist-Planner/issues
DefaultDirName={autopf}\SSP
DefaultGroupName=SSP
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\release
OutputBaseFilename=SSP-{#AppVersion}-windows-x64-setup
SetupIconFile=..\icons\icon.ico
UninstallDisplayIcon={app}\SSP.exe
UninstallDisplayName=SSP - Song and Setlist Planner
LicenseFile=..\..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Files]
Source: "..\..\dist\SSP\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\SSP - Song and Setlist Planner"; Filename: "{app}\SSP.exe"
Name: "{autodesktop}\SSP - Song and Setlist Planner"; Filename: "{app}\SSP.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SSP.exe"; Description: "Start SSP"; Flags: nowait postinstall skipifsilent
