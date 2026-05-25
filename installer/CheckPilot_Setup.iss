[Setup]
AppName=CheckPilot
AppVersion=2.5.1
AppPublisher=Pham Duy
AppPublisherURL=https://github.com/TroniePh/checkpilot
DefaultDirName={autopf}\CheckPilot
DefaultGroupName=CheckPilot
OutputDir=..\installer_output
OutputBaseFilename=CheckPilot_Setup_v2.5.1
SetupIconFile=..\assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\CheckPilot.exe
WizardStyle=modern
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional:"; Flags: unchecked
Name: "startupicon"; Description: "Start CheckPilot with Windows"; GroupDescription: "Additional:"; Flags: unchecked

[Files]
Source: "..\dist\CheckPilot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CheckPilot"; Filename: "{app}\CheckPilot.exe"
Name: "{group}\Uninstall CheckPilot"; Filename: "{uninstallexe}"
Name: "{autodesktop}\CheckPilot"; Filename: "{app}\CheckPilot.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "CheckPilot"; ValueData: """{app}\CheckPilot.exe"""; Flags: uninsdeletevalue; Tasks: startupicon

[Run]
Filename: "{app}\CheckPilot.exe"; Description: "Launch CheckPilot"; Flags: nowait postinstall skipifsilent
