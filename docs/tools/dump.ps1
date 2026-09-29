param([string]$Out="D:\r53\tree.txt", [int]$MaxDepth=8)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::RootElement
$cond=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)
$wins=$root.FindAll([System.Windows.Automation.TreeScope]::Children,$cond)
$log=New-Object System.Text.StringBuilder

function Get-Pat($e){
  $r=@()
  try{ $null=$e.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern); $r+='INV' }catch{}
  try{ $null=$e.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern); $r+='SEL' }catch{}
  try{ $null=$e.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern); $r+='VAL' }catch{}
  try{ $null=$e.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern); $r+='TXT' }catch{}
  try{ $null=$e.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern); $r+='TOG' }catch{}
  try{ $null=$e.GetCurrentPattern([System.Windows.Automation.SelectionPattern]::Pattern); $r+='SELP' }catch{}
  return ($r -join ',')
}

function Walk($e,$d){
  $ct=$e.Current.ControlType.ProgrammaticName -replace 'ControlType\.',''
  $aid=$e.Current.AutomationId
  $nm=$e.Current.Name
  if($nm.Length -gt 80){$nm=$nm.Substring(0,80)+'...'}
  $en=$e.Current.IsEnabled
  [void]$log.AppendLine(("{0}{1}|aid={2}|name={3}|en={4}|pat={5}" -f ('  '*$d),$ct,$aid,$nm,$en,(Get-Pat $e)))
  if($d -ge $MaxDepth){return}
  try{ $c=[System.Windows.Automation.TreeWalker]::ControlViewWalker.GetFirstChild($e) }catch{ $c=$null }
  while($c -ne $null){
    Walk $c ($d+1)
    try{ $c=[System.Windows.Automation.TreeWalker]::ControlViewWalker.GetNextSibling($c) }catch{ $c=$null }
  }
}

foreach($w in $wins){
  $wn=$w.Current.Name
  if($wn -notlike "KeySteam*"){continue}
  if($wn -like "*Explorer*" -or $wn -like "*资源管理器*"){continue}
  [void]$log.AppendLine("=== WINDOW: $wn | pid=$($w.Current.ProcessId) | en=$($w.Current.IsEnabled)")
  Walk $w 0
  [void]$log.AppendLine("")
}
$log.ToString()|Out-File -FilePath $Out -Encoding utf8
Write-Output "done"
