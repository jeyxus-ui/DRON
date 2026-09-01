# Reconecta Mission Planner a SITL en TCP 127.0.0.1:5760

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public class MPReconnect {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc e, IntPtr l);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, int x, int y, int d, int e);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] public static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string cls, string title);
    [DllImport("user32.dll")] public static extern int SendMessage(IntPtr h, int msg, int w, int l);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, EnumWindowsProc cb, IntPtr l);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);

    public static IntPtr FindByTitle(string fragment) {
        IntPtr found = IntPtr.Zero;
        EnumWindows((h, l) => {
            if (!IsWindowVisible(h)) return true;
            var sb = new StringBuilder(256);
            GetWindowText(h, sb, 256);
            if (sb.ToString().Contains(fragment)) { found = h; return false; }
            return true;
        }, IntPtr.Zero);
        return found;
    }

    // Encuentra boton hijo por texto
    public static IntPtr FindButton(IntPtr parent, string text) {
        IntPtr found = IntPtr.Zero;
        EnumChildWindows(parent, (h, l) => {
            var sb = new StringBuilder(128);
            GetWindowText(h, sb, 128);
            if (sb.ToString().Trim() == text) { found = h; return false; }
            return true;
        }, IntPtr.Zero);
        return found;
    }

    public static void Click(int x, int y) {
        SetCursorPos(x, y); System.Threading.Thread.Sleep(80);
        mouse_event(2, x, y, 0, 0); System.Threading.Thread.Sleep(80); mouse_event(4, x, y, 0, 0);
    }

    public static RECT GetRect(IntPtr h) { RECT r; GetWindowRect(h, out r); return r; }

    // Envia BN_CLICKED a un control (como presionar un boton sin mouse)
    public const int WM_LBUTTONDOWN = 0x0201, WM_LBUTTONUP = 0x0202;
    public const int BM_CLICK = 0x00F5;
    public static void ClickButton(IntPtr btn) { SendMessage(btn, BM_CLICK, 0, 0); }
}
'@

Write-Host "Buscando Mission Planner..."
$mp = [MPReconnect]::FindByTitle("Mission Planner")

if ($mp -eq [IntPtr]::Zero) {
    Write-Host "Mission Planner no encontrado - no se reconecto."
    exit 0
}

Write-Host "MP encontrado: hwnd=$mp"
[MPReconnect]::ShowWindow($mp, 9)
[MPReconnect]::SetForegroundWindow($mp)
Start-Sleep -Milliseconds 700

# Click en boton Connect (esquina superior derecha)
$rect = [MPReconnect]::GetRect($mp)
$connectX = $rect.Right - 55
$connectY = $rect.Top + 70
Write-Host "Click Connect en ($connectX, $connectY)..."
[MPReconnect]::Click($connectX, $connectY)

# Esperar hasta 4s que aparezca el dialogo "remote host"
$dialog = [IntPtr]::Zero
for ($i = 0; $i -lt 8; $i++) {
    Start-Sleep -Milliseconds 500
    $dialog = [MPReconnect]::FindByTitle("remote host")
    if ($dialog -ne [IntPtr]::Zero) { break }
}

if ($dialog -eq [IntPtr]::Zero) {
    Write-Host "Dialogo no aparecio - MP puede estar ya conectado o el boton estaba en otra posicion."
    exit 0
}

Write-Host "Dialogo encontrado: hwnd=$dialog"
[MPReconnect]::SetForegroundWindow($dialog)
Start-Sleep -Milliseconds 300

# Buscar boton OK dentro del dialogo
$okBtn = [MPReconnect]::FindButton($dialog, "OK")
if ($okBtn -ne [IntPtr]::Zero) {
    Write-Host "Boton OK encontrado - haciendo click..."
    [MPReconnect]::ClickButton($okBtn)
} else {
    # Fallback: click en el centro-inferior del dialogo donde suele estar OK
    $dr = [MPReconnect]::GetRect($dialog)
    $okX = $dr.Left + ($dr.Right - $dr.Left) * 3 / 4
    $okY = $dr.Top + ($dr.Bottom - $dr.Top) * 4 / 5
    Write-Host "Click fallback OK en ($okX, $okY)..."
    [MPReconnect]::Click($okX, $okY)
}

Start-Sleep -Seconds 2
Write-Host "Mission Planner reconectado a SITL."
