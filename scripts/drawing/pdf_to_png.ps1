# Render one PDF page to PNG with the Windows built-in PDF API (Windows.Data.Pdf). No extra software.
# Usage: powershell -NoProfile -File scripts\spike\pdf_to_png.ps1 -Pdf in.pdf -Png out.png [-Page 0] [-Width 2400]
#        optional crop (fractions of the page, 0..1): -CropX 0.5 -CropY 0.7 -CropW 0.5 -CropH 0.3
param(
    [Parameter(Mandatory)][string]$Pdf,
    [Parameter(Mandatory)][string]$Png,
    [int]$Page = 0,
    [int]$Width = 2400,
    [double]$CropX = 0, [double]$CropY = 0, [double]$CropW = 1, [double]$CropH = 1
)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
Add-Type -AssemblyName System.Drawing
$null = [Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]

$asTaskOp = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await-Op($op, [Type]$type) {
    $t = $asTaskOp.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait() | Out-Null; $t.Result
}
$asTaskAct = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' })[0]
function Await-Action($act) { $t = $asTaskAct.Invoke($null, @($act)); $t.Wait() | Out-Null }

$full = (Resolve-Path $Pdf).Path
$file = Await-Op ([Windows.Storage.StorageFile]::GetFileFromPathAsync($full)) ([Windows.Storage.StorageFile])
$doc = Await-Op ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) ([Windows.Data.Pdf.PdfDocument])
Write-Host ("pages: {0}" -f $doc.PageCount)
$pg = $doc.GetPage($Page)
Write-Host ("page size (1/96 in): {0:N1} x {1:N1}  = {2:N1} x {3:N1} mm" -f $pg.Size.Width, $pg.Size.Height, ($pg.Size.Width / 96 * 25.4), ($pg.Size.Height / 96 * 25.4))
$ms = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
$opt = New-Object Windows.Data.Pdf.PdfPageRenderOptions
$opt.DestinationWidth = [uint32]$Width
$opt.BackgroundColor = [Windows.UI.Colors, Windows.UI, ContentType = WindowsRuntime]::White
Await-Action ($pg.RenderToStreamAsync($ms, $opt))
$net = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($ms.GetInputStreamAt(0))
$bmp = [System.Drawing.Bitmap]::new($net)
if ($CropW -lt 1 -or $CropH -lt 1 -or $CropX -gt 0 -or $CropY -gt 0) {
    $r = [System.Drawing.Rectangle]::new([int]($bmp.Width * $CropX), [int]($bmp.Height * $CropY), [int]($bmp.Width * $CropW), [int]($bmp.Height * $CropH))
    $c = $bmp.Clone($r, $bmp.PixelFormat); $bmp.Dispose(); $bmp = $c
}
$dir = Split-Path $Png -Parent
if ($dir) { New-Item -ItemType Directory -Force $dir | Out-Null }
$Png = Join-Path (Resolve-Path $dir).Path (Split-Path $Png -Leaf)
$bmp.Save($Png, [System.Drawing.Imaging.ImageFormat]::Png)
Write-Host ("saved {0} ({1}x{2})" -f $Png, $bmp.Width, $bmp.Height)
$bmp.Dispose(); $pg.Dispose()
