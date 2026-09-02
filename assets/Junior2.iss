#ifndef SourceRoot
  #define SourceRoot "."
#endif

[Setup]
AppId={{E2811F49-18DD-48C7-A525-9FD56F2D85E9}
AppName=Junior 2.0
AppVersion=2.0.0
AppPublisher=Junior
DefaultDirName={autopf}\Junior 2.0
DefaultGroupName=Junior 2.0
OutputDir={#SourceRoot}\dist
OutputBaseFilename=Junior-2.0-Windows-x86_64-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\Junior 2.0.exe
WizardStyle=modern

[Files]
Source: "{#SourceRoot}\dist\Junior 2.0\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Junior 2.0"; Filename: "{app}\Junior 2.0.exe"
Name: "{autodesktop}\Junior 2.0"; Filename: "{app}\Junior 2.0.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\Junior 2.0.exe"; Description: "Launch Junior 2.0"; Flags: nowait postinstall skipifsilent
