param([string]$Out="D:\r53\sel.txt")
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::RootElement
$cond=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)
$wins=$root.FindAll([System.Windows.Automation.TreeScope]::Children,$cond)
$log=New-Object System.Text.StringBuilder
foreach($w in $wins){
  $nm=$w.Current.Name
  if($nm -notlike "KeySteam*"){continue}
  if($nm -like "*Explorer*" -or $nm -like "*文件资源管理器*"){continue}
  $all=$w.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
  foreach($e in $all){
    if($e.Current.ControlType.ProgrammaticName -ne "ControlType.ListItem"){continue}
    $aid=$e.Current.AutomationId
    $en=$e.Current.Name
    $ok="no"
    try{
      $p=$e.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
      $p.Select(); $ok="SEL"
    }catch{ $ok="ERR: $($_.Exception.Message)" }
    [void]$log.AppendLine("ITEM|$aid|$en|$ok")
  }
}
$log.ToString()|Out-File -FilePath $Out -Encoding utf8
Write-Output "done"
