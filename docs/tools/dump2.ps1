param([string]$Out="D:\r53\tree2.txt", [int]$MaxDepth=10, [string]$Pids="")

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$pidList = @()
if($Pids -ne ""){ $pidList = @($Pids.Split(',') | Where-Object { $_ -ne "" } | ForEach-Object { [int]$_ }) }

$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children,$cond)
$log = New-Object System.Text.StringBuilder

function Get-State($e){
  $r = @()
  try{ $p=$e.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern); $r += "TOG=" + $p.Current.ToggleState }catch{}
  try{ $p=$e.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern); $r += "SEL=" + $p.Current.IsSelected }catch{}
  return ($r -join ',')
}
function Get-Pat($e){
  $r=@()
  try{ $null=$e.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern); $r+='INV' }catch{}
  try{ $null=$e.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern); $r+='SEL' }catch{}
  try{ $null=$e.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern); $r+='TOG' }catch{}
  try{ $null=$e.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern); $r+='VAL' }catch{}
  try{ $null=$e.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern); $r+='TXT' }catch{}
  return ($r -join ',')
}
function Walk($e,$d){
  $ct=$e.Current.ControlType.ProgrammaticName -replace 'ControlType\.',''
  $aid=$e.Current.AutomationId
  $nm=$e.Current.Name
  if($nm.Length -gt 90){$nm=$nm.Substring(0,90)+'...'}
  [void]$log.AppendLine(("{0}{1}|aid={2}|name={3}|en={4}|pat={5}|{6}" -f ('  '*$d),$ct,$aid,$nm,$e.Current.IsEnabled,(Get-Pat $e),(Get-State $e)))
  if($d -ge $MaxDepth){return}
  try{ $c=[System.Windows.Automation.TreeWalker]::ControlViewWalker.GetFirstChild($e) }catch{ $c=$null }
  while($c -ne $null){
    Walk $c ($d+1)
    try{ $c=[System.Windows.Automation.TreeWalker]::ControlViewWalker.GetNextSibling($c) }catch{ $c=$null }
  }
}

foreach($w in $wins){
  $wn = $w.Current.Name
  $wp = $w.Current.ProcessId
  $keep = $false
  if($pidList.Count -gt 0){
    if($pidList -contains $wp){ $keep = $true }
  } else {
    if($wn -like "KeySteam*" -and $wn -notlike "*Explorer*" -and $wn -notlike "*资源管理器*"){ $keep = $true }
  }
  if(-not $keep){ continue }
  [void]$log.AppendLine("=== WINDOW: '$wn' | pid=$wp | en=$($w.Current.IsEnabled)")
  Walk $w 0
  [void]$log.AppendLine("")
}
$log.ToString() | Out-File -FilePath $Out -Encoding utf8
Write-Output "done"
