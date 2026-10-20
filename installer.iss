; Script for Inno Setup 6
; Contract Manager Installer
#define MyAppName "Contract Manager"
#define MyAppPublisher "Greek Contract Manager"
#define MyAppURL "https://github.com/grcomandos83-cyber/Greek-Contract-Manager"
#define MyAppExeName "ContractManager.exe"

#ifndef MyAppVersion
#define MyAppVersion "1.0.27"
#endif

[Setup]
; Unique GUID for the application
AppId={{D37F299B-510E-481E-B474-9C74E049A321}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\ContractManager
DisableProgramGroupPage=yes
; Per-user install: no admin rights required, prevents UAC elevation prompts during updates
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=ContractManager_Setup
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "launcher.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\app.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\app.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\assets\app.ico"

[Run]
Filename: "{app}\launcher.bat"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: runhidden nowait postinstall skipifsilent; Check: ShouldLaunchInteractive
Filename: "{app}\launcher.bat"; Flags: runhidden nowait; Check: ShouldLaunchSilent

[Code]
function ShouldLaunchSilent(): Boolean;
begin
  Result := WizardSilent();
end;

function ShouldLaunchInteractive(): Boolean;
begin
  Result := not WizardSilent();
end;
