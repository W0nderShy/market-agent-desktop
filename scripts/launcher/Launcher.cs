using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Windows.Forms;
using System.Runtime.InteropServices;

internal static class Launcher {
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr hWnd, int command);
    static string FindProjectRoot() {
        string location = AppDomain.CurrentDomain.BaseDirectory;
        if (File.Exists(Path.Combine(location, "scripts", "start.ps1"))) return location;
        string sibling = Path.Combine(location, "AI_back");
        if (File.Exists(Path.Combine(sibling, "scripts", "start.ps1"))) return sibling;
        throw new FileNotFoundException("未找到交易终端工程。请把启动器放在 AI_back 工程目录，或放在 AI_back 的上一级目录。", "scripts/start.ps1");
    }
    [STAThread] static int Main() {
        bool acquired;
        using (var mutex = new Mutex(true, @"Local\DshMarketDesktopLauncher", out acquired)) {
            if (!acquired) return 0;
            try {
                string root = FindProjectRoot();
                foreach (var process in Process.GetProcessesByName("electron")) {
                    using (process) {
                        try {
                            if (process.MainWindowHandle != IntPtr.Zero && process.MainModule.FileName.StartsWith(Path.Combine(root, "vendor") + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) {
                                ShowWindow(process.MainWindowHandle, 9);
                                SetForegroundWindow(process.MainWindowHandle);
                                return 0;
                            }
                        } catch (System.ComponentModel.Win32Exception) { } catch (InvalidOperationException) { }
                    }
                }
                string script = Path.Combine(root, "scripts", "start.ps1");
                if (!File.Exists(Path.Combine(root, ".venv", "Scripts", "python.exe")) ||
                    !File.Exists(Path.Combine(root, "vendor", "deepseek-harness", "apps", "desktop", "node_modules", "electron", "dist", "electron.exe"))) {
                    throw new Exception("交易终端尚未安装依赖。请先在 " + root + " 运行 scripts\\setup.ps1，然后再次双击启动器。");
                }
                var info = new ProcessStartInfo {
                    FileName = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), @"WindowsPowerShell\v1.0\powershell.exe"),
                    Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"" + script + "\"",
                    WorkingDirectory = root,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden
                };
                using (var child = Process.Start(info)) {
                    child.WaitForExit();
                    if (child.ExitCode != 0) throw new Exception("启动未成功。请检查项目依赖或 runtime 目录中的启动日志。");
                }
                return 0;
            } catch (Exception error) {
                MessageBox.Show(error.Message, "Trading Terminal", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            } finally { mutex.ReleaseMutex(); }
        }
    }
}
