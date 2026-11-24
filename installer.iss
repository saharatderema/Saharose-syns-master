#define AppName "SAHARoseSyncMaster"
#define AppVersion "1.0.0"

[Setup]
AppId={{11E211A7-0A4D-4C52-95CE-028792BA9F76}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=Setup_SAHARoseSyncMaster
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\SAHARoseSyncMaster.exe

[Files]
Source: "dist\SAHARoseSyncMaster\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "config.example.json"; DestDir: "{app}"; DestName: "config.json"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\SAHARoseSyncMaster"; Filename: "{app}\SAHARoseSyncMaster.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\SAHARoseSyncMaster"; Filename: "{app}\SAHARoseSyncMaster.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\SAHARoseSyncMaster.exe"; Description: "Launch SAHARoseSyncMaster"; Flags: postinstall nowait skipifsilent
