#define MyAppName "CheckPilot"
#define MyAppVersion "2.6.1"
#define MyAppPublisher "CheckPilot"
#define MyAppExeName "CheckPilot.exe"

[Setup]
AppId={{7D5FA51E-4CE9-4F44-A5B7-8D5A48C9A241}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=no
OutputDir=..\release
OutputBaseFilename=CheckPilot_Setup_v{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
; ── Auto-update support ──
; Allow silent upgrade over existing installation
CloseApplications=force
CloseApplicationsFilter=CheckPilot.exe
RestartApplications=yes
; Don't ask "app is running" — just close it
AppMutex=CheckPilot_SingleInstance_7D5FA51E

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\CheckPilot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CheckPilot"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\CheckPilot"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch CheckPilot"; Flags: nowait postinstall skipifsilent
