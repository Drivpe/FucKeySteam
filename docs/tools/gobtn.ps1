param([string]$Out="D:\r53\btn.txt", [string]$AidSub="updateLuaBtn")
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::RootElement
$cond=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)
$wins=$root.FindAll([System.Windows.Automation.TreeScope]::Children,$cond)
$log=New-Object System.Text.StringBuilder
foreach($w in $wins){
  $wn=$w.Current.Name
  if($wn -notlike "KeySteam*"){continue}
  if($wn -like "*Explorer*" -or $wn -like "*资源管理器*"){continue}
  $all=$w.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
  foreach($e in $all){
    if($e.Current.ControlType.ProgrammaticName -ne "ControlType.Button"){continue}
    if($e.Current.AutomationId -notlike "*$AidSub*"){continue}
    $en=$e.Current.IsEnabled
    if(-not $en){
      [void]$log.AppendLine("SKIP|$($e.Current.Name)|$AidSub|en=False  ← 未启用，拒绝点击")
      continue
    }
    $ok="no-pattern"
    try{
      $p=$e.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
      $p.Invoke(); $ok="INVOKED"
    }catch{ $ok="ERR: $($_.Exception.Message)" }
    [void]$log.AppendLine("GO|$($e.Current.Name)|$AidSub|en=$en|$ok")
  }
}
$log.ToString()|Out-File -FilePath $Out -Encoding utf8
Write-Output "done"
