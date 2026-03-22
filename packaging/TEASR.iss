[Setup]
AppId={{3C89E374-6B1D-4F9D-B06D-4B690E8CF7A6}
AppName=TEASR
AppVersion=0.1.0
DefaultDirName={autopf}\TEASR
DefaultGroupName=TEASR
OutputDir=installer
OutputBaseFilename=TEASR-Setup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
SetupIconFile=TEASR.ico
UninstallDisplayIcon={app}\TEASR.exe
PrivilegesRequired=lowest

[Files]
Source: "dist\TEASR\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\TEASR"; Filename: "{app}\TEASR.exe"
Name: "{autodesktop}\TEASR"; Filename: "{app}\TEASR.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\TEASR.exe"; Description: "Launch TEASR"; Flags: nowait postinstall skipifsilent
