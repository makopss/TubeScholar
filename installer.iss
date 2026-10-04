; TubeScholar Inno Setup Installation Script
; Generates TubeScholar-Setup-v1.0.0.exe

#define MyAppName "TubeScholar"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "TubeScholar Team"
#define MyAppURL "https://github.com/makop/TubeScholar"
#define MyAppExeName "TubeScholar.exe"

[Setup]
; App Information
AppId={{D8A68FA8-52EF-4F54-BF27-1110595CFEE0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Installation directory
; autopf: 일반 사용자 계정일 경우 LocalAppData\Programs, 관리자일 경우 Program Files
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Output Configuration
OutputDir=dist\installer
OutputBaseFilename=TubeScholar-Setup-v1.0.0
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; Privileges: lowest를 사용하여 일반 권한 사용자도 UAC 경고 없이 안전하게 설치 가능
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; UI & Icons
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\app_icon.ico
ChangesAssociations=yes
CloseApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\TubeScholar\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"; IconFilename: "{app}\app_icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\app_icon.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// 설치 시작 전 실행 중인 TubeScholar.exe 자동 강제 종료
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM TubeScholar.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(300);
  Result := True;
end;

// 설치 준비 단계(파일 복사 직전)에서도 확실히 종료
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM TubeScholar.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(300);
  Result := '';
end;

// 프로그램 삭제(Uninstall) 시에도 실행 중인 프로세스 먼저 종료
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM TubeScholar.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(300);
  Result := True;
end;
