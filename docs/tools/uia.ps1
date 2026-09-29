param([string]$Out="D:\r53\uiadump.txt")
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::RootElement
$cond=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)
$wins=$root.FindAll([System.Windows.Automation.TreeScope]::Children,$cond)
$sb=New-Object System.Text.StringBuilder
foreach($w in $wins){
  $nm=$w.Current.Name
  $p=$w.Current.ProcessId
  if($nm -like "KeySteam*" -and $nm -notlike "*文件资源管理器*" -and $nm -notlike "*Explorer*"){
    $r=$w.Current.BoundingRectangle
    [void]$sb.AppendLine("WIN|$p|$nm|$([int]$r.X)|$([int]$r.Y)|$([int]$r.Width)|$([int]$r.Height)")
    $all=$w.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
    foreach($e in $all){
      $ct=$e.Current.ControlType.ProgrammaticName
      $n=$e.Current.Name
      $r=$e.Current.BoundingRectangle
      $cx=[int]($r.X+$r.Width/2); $cy=[int]($r.Y+$r.Height/2)
      $aid=$e.Current.AutomationId
      [void]$sb.AppendLine("ELEM|$p|$ct|$aid|$n|$cx|$cy|$([int]$r.Width)x$([int]$r.Height)")
    }
  }
}
$sb.ToString()|Out-File -FilePath $Out -Encoding utf8
Write-Output "ok"
