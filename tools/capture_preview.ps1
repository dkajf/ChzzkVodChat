param(
    [string]$Python = "$env:LOCALAPPDATA/Python/pythoncore-3.14-64/python.exe"
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class CvcPreviewWindow {
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window, out Rect rect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr window, IntPtr dc, uint flags);
}
'@
$cvcRoot = Split-Path -Parent $PSScriptRoot
$cvcOutput = Join-Path $cvcRoot 'build/preview'
New-Item -ItemType Directory -Force -Path $cvcOutput | Out-Null
foreach ($cvcMode in @('empty', 'collect', 'txt', 'options')) {
    $cvcArgs = @('tools/preview_gui.py')
    if ($cvcMode -ne 'collect') { $cvcArgs += "--$cvcMode" }
    $cvcProcess = Start-Process -FilePath $Python -ArgumentList $cvcArgs -WorkingDirectory $cvcRoot -WindowStyle Hidden -PassThru
    try {
        for ($cvcTry = 0; $cvcTry -lt 30; $cvcTry++) {
            Start-Sleep -Milliseconds 300
            $cvcProcess.Refresh()
            if ($cvcProcess.MainWindowTitle -eq 'ChzzkVodChat v2.0') { break }
        }
        Start-Sleep -Milliseconds 900
        $cvcProcess.Refresh()
        $cvcRect = New-Object CvcPreviewWindow+Rect
        if (-not [CvcPreviewWindow]::GetWindowRect($cvcProcess.MainWindowHandle, [ref]$cvcRect)) { throw 'Preview window not found' }
        $cvcBitmap = New-Object System.Drawing.Bitmap ($cvcRect.Right - $cvcRect.Left), ($cvcRect.Bottom - $cvcRect.Top)
        $cvcGraphics = [System.Drawing.Graphics]::FromImage($cvcBitmap)
        $cvcDc = $cvcGraphics.GetHdc()
        try {
            if (-not [CvcPreviewWindow]::PrintWindow($cvcProcess.MainWindowHandle, $cvcDc, 2)) { throw 'Window capture failed' }
        } finally { $cvcGraphics.ReleaseHdc($cvcDc) }
        $cvcBitmap.Save((Join-Path $cvcOutput "$cvcMode.png"), [System.Drawing.Imaging.ImageFormat]::Png)
        $cvcGraphics.Dispose()
        $cvcBitmap.Dispose()
        Write-Output "Captured $cvcMode"
    } finally {
        $cvcProcess.Refresh()
        if (-not $cvcProcess.HasExited) {
            $cvcProcess.CloseMainWindow() | Out-Null
            $cvcProcess.WaitForExit(10000) | Out-Null
        }
    }
}
