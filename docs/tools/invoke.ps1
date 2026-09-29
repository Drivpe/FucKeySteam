param([string]$Name="", [string]$AidSub="", [string]$Out="D:\r53\invoke.txt")
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
    if($ct -ne "ControlType.Button"){ continue }
    $en=$e.Current.Name
    $aid=$e.Current.AutomationId
    $match=$false
    if($Name -ne "" -and $en -eq $Name){ $match=$true }
    if($AidSub -ne "" -and $aid -like "*$AidSub*"){ $match=$true }
    if(-not $match){ continue }
    $ok="no-pattern"
    try{
      $p=$e.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
      $p.Invoke(); $ok="INVOKED"
    }catch{ $ok="ERR: $($_.Exception.Message)" }
    [void]$log.AppendLine("BTN|$en|$aid|$ok")
  }
}
$log.ToString()|Out-File -FilePath $Out -Encoding utf8
Write-Output "done"
