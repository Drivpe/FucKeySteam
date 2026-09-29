param([string]$AppID="", [int]$Index=-1, [string]$Out="D:\r53\selone.txt")
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
    if($e.Current.ControlType.ProgrammaticName -eq "ControlType.ListItem" -and $e.Current.AutomationId -like "*gamesSurface*"){ $items+=$e }
  }
  [void]$log.AppendLine("TOTAL|$($items.Count)")
  # 先全部反选（点第一项前的安全做法：只 Select 目标项，Qt 默认单选）
  $n=0
  foreach($e in $items){
    $nm=$e.Current.Name
    $hit=$false
    if($AppID -ne "" -and $nm -like "*($AppID)*"){ $hit=$true }
    if($Index -ge 0 -and $n -eq $Index){ $hit=$true }
    if($hit){
      $ok="none"
      try{
        $p=$e.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
        $p.Select(); $ok="Select"
      }catch{ $ok="ERR: $($_.Exception.Message)" }
      [void]$log.AppendLine("PICKED|$n|$nm|$ok")
    }
    $n++
  }
  # 回读选中状态
  [void]$log.AppendLine("--- 选中状态 ---")
  foreach($e in $items){
    $s="?"
    try{ $p=$e.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern); $s=$p.Current.IsSelected }catch{}
    [void]$log.AppendLine("STATE|$($e.Current.Name)|$s")
  }
}
$log.ToString()|Out-File -FilePath $Out -Encoding utf8
Write-Output "done"
