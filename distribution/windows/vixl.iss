#ifndef VixlVersion
  #error VixlVersion is required
#endif
#ifndef SourceRoot
  #define SourceRoot "..\.."
#endif
[Setup]
AppId={{B0F6895F-05DA-4E86-A2CD-23D298519493}
AppName=Vixl
AppVersion={#VixlVersion}
AppPublisher=Vixl contributors
AppPublisherURL=https://github.com/jxburros/Vixl
AppSupportURL=https://github.com/jxburros/Vixl/issues
AppUpdatesURL=https://github.com/jxburros/Vixl/releases
DefaultDirName={localappdata}\Programs\Vixl
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#SourceRoot}\dist\release
OutputBaseFilename=Vixl-Setup-{#VixlVersion}-windows-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ChangesEnvironment=yes
CloseApplications=no
RestartApplications=no
UninstallDisplayName=Vixl
SetupIconFile={#SourceRoot}\distribution\windows\vixl.ico
UninstallDisplayIcon={app}\bin\vixl.exe

[Tasks]
; Optional and off by default: a per-user Scheduled Task, so no admin rights (a Windows service would need them).
Name: "studiohost"; Description: "Run Vixl host for AI Server Studio (starts at logon, loopback only)"; Flags: unchecked

[Files]
Source: "{#SourceRoot}\dist\launcher\vixl.exe"; DestDir: "{app}\bin"; Flags: ignoreversion
; Second copy in the per-user WindowsApps folder, which Windows 10/11 already puts on the
; user PATH, so terminals and agents started before installation find vixl at once.
; ShouldInstallAlias never replaces another program's vixl.exe; the uninstaller removes
; this copy itself (only when it still matches bin\vixl.exe), hence uninsneveruninstall.
Source: "{#SourceRoot}\dist\launcher\vixl.exe"; DestDir: "{localappdata}\Microsoft\WindowsApps"; Flags: ignoreversion uninsneveruninstall; Check: ShouldInstallAlias
; Registers or removes the "Vixl host" task; installed always, so the uninstaller can remove a task an earlier install made.
Source: "{#SourceRoot}\distribution\windows\host-task.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\dist\runtime\vixl-engine\*"; DestDir: "{app}\versions\{#VixlVersion}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Vixl"; Filename: "{app}\bin\vixl.exe"; WorkingDir: "{userdocs}"
Name: "{userprograms}\Uninstall Vixl"; Filename: "{uninstallexe}"

[Registry]
; Lets the WindowsApps copy of the launcher find a non-default installation folder.
Root: HKCU; Subkey: "Software\Vixl"; ValueType: string; ValueName: "InstallRoot"; ValueData: "{app}"; Flags: uninsdeletevalue uninsdeletekeyifempty

[UninstallRun]
; Stops and unregisters the "Vixl host" task and deletes host.json and its token; workspaces under Vixl\host stay.
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\host-task.ps1"" -Action Remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveVixlHostTask"

[UninstallDelete]
; Only installer-managed data. User projects and AI configuration are never removed.
Type: filesandordirs; Name: "{app}\versions"
Type: filesandordirs; Name: "{app}\update-work"
Type: files; Name: "{app}\install.json"
Type: files; Name: "{app}\.update.lock"
Type: files; Name: "{app}\.vixl-*.tmp"

[Code]
var
  AliasDecided, AliasWanted: Boolean;

function AliasDir(): String;
begin
  Result := ExpandConstant('{localappdata}\Microsoft\WindowsApps');
end;

function AliasFile(): String;
begin
  Result := AliasDir() + '\vixl.exe';
end;

{ Expands %NAME% references, as stored in REG_EXPAND_SZ PATH values. }
function ExpandEnvironment(Value: String): String;
var
  Rest, VarName: String;
  StartAt, EndAt: Integer;
begin
  Result := '';
  Rest := Value;
  StartAt := Pos('%', Rest);
  while StartAt > 0 do
  begin
    Result := Result + Copy(Rest, 1, StartAt - 1);
    Rest := Copy(Rest, StartAt + 1, Length(Rest));
    EndAt := Pos('%', Rest);
    if EndAt = 0 then
    begin
      Result := Result + '%';
      StartAt := 0;
    end
    else
    begin
      VarName := Copy(Rest, 1, EndAt - 1);
      if (VarName <> '') and (GetEnv(VarName) <> '') then
        Result := Result + GetEnv(VarName)
      else
        Result := Result + '%' + VarName + '%';
      Rest := Copy(Rest, EndAt + 1, Length(Rest));
      StartAt := Pos('%', Rest);
    end;
  end;
  Result := Result + Rest;
end;

function PathContains(Value, Folder: String): Boolean;
var
  StartAt, EndAt: Integer;
begin
  Result := False;
  StartAt := 1;
  while (StartAt <= Length(Value)) and not Result do
  begin
    EndAt := StartAt;
    while (EndAt <= Length(Value)) and (Value[EndAt] <> ';') do EndAt := EndAt + 1;
    if CompareText(RemoveBackslashUnlessRoot(Trim(ExpandEnvironment(Copy(Value, StartAt, EndAt - StartAt)))), Folder) = 0 then
      Result := True;
    StartAt := EndAt + 1;
  end;
end;

function SameFileContents(First, Second: String): Boolean;
begin
  Result := False;
  if FileExists(First) and FileExists(Second) then
    try
      Result := CompareText(GetSHA256OfFile(First), GetSHA256OfFile(Second)) = 0;
    except
      Result := False;
    end;
end;

{ Decided once, before any file is copied: the alias is ours to write only if the folder
  exists and is on PATH, and there is no vixl.exe there or it is byte-identical to the
  launcher of the installation being upgraded (bin\vixl.exe is never self-updated). }
function ShouldInstallAlias(): Boolean;
var
  UserPath: String;
begin
  if not AliasDecided then
  begin
    AliasDecided := True;
    AliasWanted := False;
    if DirExists(AliasDir()) then
    begin
      if not RegQueryStringValue(HKCU, 'Environment', 'Path', UserPath) then UserPath := '';
      if PathContains(UserPath, AliasDir()) or PathContains(GetEnv('PATH'), AliasDir()) then
        AliasWanted := (not FileExists(AliasFile()))
          or SameFileContents(AliasFile(), ExpandConstant('{app}\bin\vixl.exe'));
    end;
    if AliasWanted then
      Log('Installing the vixl command alias in ' + AliasDir())
    else
      Log('Not installing the vixl command alias in ' + AliasDir());
  end;
  Result := AliasWanted;
end;

function WithoutVixlPath(Value: String): String;
var
  BinPath: String;
  StartAt, EndAt: Integer;
begin
  Result := Value;
  BinPath := ExpandConstant('{app}\bin');
  StartAt := 1;
  while StartAt <= Length(Result) do
  begin
    EndAt := StartAt;
    while (EndAt <= Length(Result)) and (Result[EndAt] <> ';') do EndAt := EndAt + 1;
    if CompareText(RemoveBackslashUnlessRoot(Trim(Copy(Result, StartAt, EndAt - StartAt))), BinPath) = 0 then
    begin
      if EndAt <= Length(Result) then
        Delete(Result, StartAt, EndAt - StartAt + 1)
      else if StartAt > 1 then
        Delete(Result, StartAt - 1, EndAt - StartAt + 1)
      else Result := '';
    end
    else StartAt := EndAt + 1;
  end;
end;

{ The studiohost task: host-task.ps1 generates the 32-byte token (Pascal Script has no secure random source), writes it
  and %LOCALAPPDATA%\Vixl\host.json readable by this user only, and registers and starts the per-user task. A
  failure is reported, never fatal: Vixl itself is installed. }
procedure RegisterHostTask();
var
  Code: Integer;
begin
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
              '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\host-task.ps1') +
              '" -Action Install -App "' + ExpandConstant('{app}') + '"',
              ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
    SuppressibleMsgBox('Vixl is installed, but the Vixl host task for AI Server Studio could not be registered (code ' +
                       IntToStr(Code) + '). See docs/reference/releases.md, "Vixl host for AI Server Studio".',
                       mbError, MB_OK, IDOK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
  ExistingPath, UpdatedPath: String;
begin
  if CurStep = ssInstall then
    ShouldInstallAlias();
  if CurStep = ssPostInstall then
  begin
    if not Exec(ExpandConstant('{app}\bin\vixl.exe'), '--vixl-install {#VixlVersion}',
                ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) then
      RaiseException('Vixl could not initialize. Please run the installer again.');
    if Code <> 0 then
      RaiseException('Vixl did not pass its installation check. Your previous version was kept.');
    RegQueryStringValue(HKCU, 'Environment', 'Path', ExistingPath);
    UpdatedPath := ExpandConstant('{app}\bin');
    ExistingPath := WithoutVixlPath(ExistingPath);
    if ExistingPath <> '' then UpdatedPath := UpdatedPath + ';' + ExistingPath;
    if not RegWriteExpandStringValue(HKCU, 'Environment', 'Path', UpdatedPath) then
      RaiseException('Could not update your user PATH.');
    if WizardIsTaskSelected('studiohost') then
      RegisterHostTask();
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ExistingPath: String;
begin
  { Before bin\vixl.exe is removed: delete the alias only if it is still our launcher. }
  if (CurUninstallStep = usUninstall)
     and SameFileContents(AliasFile(), ExpandConstant('{app}\bin\vixl.exe')) then
    if not DeleteFile(AliasFile()) then
      Log('Could not remove ' + AliasFile() + '; it may be running.');
  if CurUninstallStep = usPostUninstall then
    if RegQueryStringValue(HKCU, 'Environment', 'Path', ExistingPath) then
      RegWriteExpandStringValue(HKCU, 'Environment', 'Path', WithoutVixlPath(ExistingPath));
end;
