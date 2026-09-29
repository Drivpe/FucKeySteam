param([string]$Set = "", [string]$Out = "D:\r53\edit.txt")
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::RootElement
$cond=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)
$wins=$root.FindAll([System.Windows.Automation.TreeScope]::Children,$cond)
$log=New-Object System.Text.StringBuilder
foreach($w in $wins){
  if($w.Current.Name -notlike "KeySteam*"){ continue }
  $all=$w.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
  foreach($e in $all){
    $ct=$e.Current.ControlType.ProgrammaticName
    $aid=$e.Current.AutomationId
    $nm=$e.Current.Name
    $val=""
    try{ $vp=$e.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern); $val=$vp.Current.Value }catch{}
    $tx=""
    try{ $tp=$e.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern); $tx=$tp.DocumentRange.GetText(4000) }catch{}
    if($ct -eq "ControlType.Edit" -or $ct -eq "ControlType.Document" -or $tx -ne ""){
      [void]$log.AppendLine("EDIT|$ct|$aid|name=$nm|val=$val|text=$($tx -replace "`r`n","\n")")
    }
    if($Set -ne "" -and $ct -eq "ControlType.Edit"){
      try{ $vp=$e.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern); $vp.SetValue($Set); [void]$log.AppendLine("SET|$aid|ok") }catch{ [void]$log.AppendLine("SET|$aid|ERR $($_.Exception.Message)") }
      break
    }
  }
}
$log.ToString()|Out-File -FilePath $Out -Encoding utf8
Write-Output "done"
