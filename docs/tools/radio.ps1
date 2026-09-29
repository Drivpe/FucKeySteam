param([string]$Name="", [string]$Out="D:\r53\radio.txt")
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
    if($e.Current.ControlType.ProgrammaticName -ne "ControlType.RadioButton"){continue}
    $en=$e.Current.Name
    $enabled=$e.Current.IsEnabled
    if($Name -ne "" -and $en -ne $Name){continue}
    $ok="none"
    if(-not $enabled){ $ok="SKIP(en=False)" }
    else{
      try{
        $p=$e.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
        $p.Select(); $ok="SEL"
      }catch{
        try{ $t=$e.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern); $t.Toggle(); $ok="TOG" }
        catch{ $ok="ERR: $($_.Exception.Message)" }
      }
    }
    [void]$log.AppendLine("RADIO|$en|en=$enabled|$ok")
  }
}
$log.ToString()|Out-File -FilePath $Out -Encoding utf8
Write-Output "done"
