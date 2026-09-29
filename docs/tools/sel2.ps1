param([string]$Out="D:\r53\sel2.txt", [string]$Mode="all")
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
  $items=@()
  foreach($e in $all){
    if($e.Current.ControlType.ProgrammaticName -eq "ControlType.ListItem" -and $e.Current.AutomationId -like "*gamesSurface*"){
      $items+=$e
    }
  }
  [void]$log.AppendLine("TOTAL|$($items.Count)")
  $i=0
  foreach($e in $items){
    $nm=$e.Current.Name
    $ok="none"
    try{
      $p=$e.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
      if($i -eq 0){
        $p.Select(); $ok="Select"
      } else {
        try{ $p.AddToSelection(); $ok="AddToSelection" }
        catch{ $p.Select(); $ok="Select(fallback)" }
      }
    }catch{ $ok="ERR: $($_.Exception.Message)" }
    [void]$log.AppendLine("SEL|$i|$nm|$ok")
    $i++
  }
  [void]$log.AppendLine("--- 按钮状态 ---")
  foreach($e in $all){
    if($e.Current.ControlType.ProgrammaticName -ne "ControlType.Button"){continue}
    $aid=$e.Current.AutomationId
    if($aid -like "*updateLuaBtn*" -or $aid -like "*dangerGhostButton*"){
      [void]$log.AppendLine("BTN|$($e.Current.Name)|$aid|en=$($e.Current.IsEnabled)")
    }
  }
}
$log.ToString()|Out-File -FilePath $Out -Encoding utf8
Write-Output "done"
