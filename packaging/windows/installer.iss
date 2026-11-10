; Inno Setup script for Barline - Song and Setlist Planner (Windows).
; Build:  ISCC /DAppVersion=0.10.0 packaging\windows\installer.iss   (after pyinstaller)
; Per-user install: no administrator needed. Songs are not in the program
; folder (they live in %APPDATA%\SingleSongPlanner), so uninstalling or
; updating never touches them.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{68A4579C-2AED-4FD0-AE62-3A4F81AF74D4}
AppName=Barline - Song and Setlist Planner
AppVersion={#AppVersion}
AppPublisher=giopas
AppPublisherURL=https://github.com/giopas/barline
AppSupportURL=https://github.com/giopas/barline/issues
DefaultDirName={autopf}\Barline
DefaultGroupName=Barline
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\release
OutputBaseFilename=Barline-{#AppVersion}-windows-x64-setup
SetupIconFile=..\icons\icon.ico
UninstallDisplayIcon={app}\Barline.exe
UninstallDisplayName=Barline - Song and Setlist Planner
LicenseFile=..\..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Files]
Source: "..\..\dist\Barline\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Barline - Song and Setlist Planner"; Filename: "{app}\Barline.exe"
Name: "{autodesktop}\Barline - Song and Setlist Planner"; Filename: "{app}\Barline.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Barline.exe"; Description: "Start Barline"; Flags: nowait postinstall skipifsilent
