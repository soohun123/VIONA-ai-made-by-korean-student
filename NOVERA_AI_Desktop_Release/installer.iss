[Setup]
AppId={{302881F9-B378-4E7B-8597-E594C5721210}
AppName=NOVERA AI Desktop
#ifndef ForgeAppVersion
AppVersion=1.2.7
#else
AppVersion={#ForgeAppVersion}
#endif
AppPublisher=NOVERA / VIONA
DefaultDirName={autopf}\NOVERA AI Desktop
DefaultGroupName=NOVERA AI Desktop
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableDirPage=no
WizardStyle=modern
OutputDir=artifacts
OutputBaseFilename=NOVERA_AI_Setup
SetupIconFile=assets\novera.ico
UninstallDisplayIcon={app}\NOVERA_AI_Desktop.exe
Compression=lzma2/fast
SolidCompression=no
LZMANumBlockThreads=2
CloseApplications=yes
RestartApplications=no
LicenseFile=licenses\DISTRIBUTION.txt

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\NOVERA_AI_Desktop\*"; DestDir: "{app}"; Excludes: "\model-pack\*"; Flags: ignoreversion recursesubdirs createallsubdirs
#ifndef ForgeAdapterHash
Source: "model-pack\*"; DestDir: "{app}\model-pack"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs uninsneveruninstall
#else
Source: "model-pack\models\qwen\model.gguf"; DestDir: "{app}\model-pack\models\qwen"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "model-pack\adapters\text\{#ForgeAdapterHash}.gguf"; DestDir: "{app}\model-pack\adapters\text"; Flags: onlyifdoesntexist uninsneveruninstall
#endif
Source: "USER_GUIDE_KO.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "prerequisites\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; DestDir: "{tmp}"; Flags: dontcopy

[Icons]
Name: "{group}\NOVERA AI Desktop"; Filename: "{app}\NOVERA_AI_Desktop.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\NOVERA AI Desktop"; Filename: "{app}\NOVERA_AI_Desktop.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\NOVERA_AI_Desktop.exe"; Description: "Launch NOVERA AI Desktop"; Flags: nowait postinstall skipifsilent

[Code]
function NeedsWebView2: Boolean;
var Version: String;
begin
  Result := True;
  if RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) then
    if (Version <> '') and (Version <> '0.0.0.0') then Result := False;
  if RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) then
    if (Version <> '') and (Version <> '0.0.0.0') then Result := False;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var ExitCode: Integer;
begin
  Result := '';
  if NeedsWebView2 then begin
    ExtractTemporaryFile('MicrosoftEdgeWebView2RuntimeInstallerX64.exe');
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      Result := 'Microsoft WebView2 Runtime could not be started.'
    else if ExitCode <> 0 then
      Result := 'Microsoft WebView2 Runtime installation failed. Exit code: ' + IntToStr(ExitCode);
  end else Log('Existing WebView2 Runtime detected; installation skipped.');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) then
    MsgBox('Your conversations, settings and models have been preserved. User data: ' + ExpandConstant('{localappdata}\NOVERA AI Desktop') + #13#10 + 'Bundled models: ' + ExpandConstant('{app}\model-pack'), mbInformation, MB_OK);
end;
