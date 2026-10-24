using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
namespace OfflineCaptionsSetup;
internal static class Program {
    static Stream Payload()=>Assembly.GetExecutingAssembly().GetManifestResourceStream("Payload.zip")??throw new IOException("安裝包缺少程式檔案");
    static void Extract(string destination){using var stream=Payload();using var zip=new ZipArchive(stream,ZipArchiveMode.Read);zip.ExtractToDirectory(destination,true);}
    [STAThread] static int Main(string[] args){
        if(args.Length==2&&args[0]=="--verify-payload"){
            try {using var stream=Payload();using var zip=new ZipArchive(stream,ZipArchiveMode.Read);var required=new[]{"OfflineCaptions.exe","OfflineCapture.dll","runtime/python.exe","backend/worker.py","models/sensevoice-small-int8/model.int8.onnx","models/sensevoice-small-int8/tokens.txt","models/opus-en-zh/model.bin"};foreach(var name in required)if(zip.GetEntry(name) is null)throw new IOException("Missing: "+name);if(zip.Entries.Any(e=>e.FullName.StartsWith("models/whisper-",StringComparison.OrdinalIgnoreCase)))throw new IOException("Unexpected legacy Whisper weights");File.WriteAllText(args[1],$"PASS: SenseVoice installer payload contains {zip.Entries.Count} files and all required components.");return 0;}catch(Exception e){File.WriteAllText(args[1],e.ToString());return 1;}
        }
        var app=new Application();
        var destination=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs","OfflineCaptions");
        var window=new Window{Title="安裝離線即時字幕",Width=560,Height=360,ResizeMode=ResizeMode.NoResize,WindowStartupLocation=WindowStartupLocation.CenterScreen,Background=new SolidColorBrush(Color.FromRgb(243,245,244)),FontFamily=new FontFamily("Microsoft JhengHei UI")};
        var panel=new StackPanel{Margin=new Thickness(30)};
        panel.Children.Add(new TextBlock{Text="離線即時字幕",FontSize=26,FontWeight=FontWeights.SemiBold,Margin=new Thickness(0,0,0,18)});
        var status=new TextBlock{Text="安裝桌面程式、Python 執行環境與中英離線模型。\n不需要管理員權限，也不需要雲端 API。",TextWrapping=TextWrapping.Wrap,FontSize=14,Margin=new Thickness(0,0,0,15)};panel.Children.Add(status);
        panel.Children.Add(new TextBlock{Text=destination,Foreground=Brushes.SlateGray,FontSize=11,TextWrapping=TextWrapping.Wrap});
        var progress=new ProgressBar{Height=5,Margin=new Thickness(0,18,0,18),Visibility=Visibility.Collapsed};panel.Children.Add(progress);
        var install=new Button{Content="安裝並開啟",Padding=new Thickness(16,10,16,10),HorizontalAlignment=HorizontalAlignment.Left,Margin=new Thickness(0,18,0,0)};panel.Children.Add(install);window.Content=panel;
        bool installing=false;
        window.Closing+=(_,e)=>{if(installing)e.Cancel=true;};
        install.Click+=async(_,_)=>{
            if(Process.GetProcessesByName("OfflineCaptions").Length>0){status.Text="請先關閉正在執行的離線即時字幕，再安裝。";return;}
            installing=true;install.IsEnabled=false;progress.Visibility=Visibility.Visible;progress.IsIndeterminate=true;status.Text="正在解壓與安裝，請稍候…";
            string stage=destination+".staging-"+Guid.NewGuid().ToString("N"),backup=destination+".previous-"+DateTime.Now.ToString("yyyyMMddHHmmss");
            try{
                await Task.Run(()=>{
                    Directory.CreateDirectory(Path.GetDirectoryName(destination)!);Extract(stage);
                    if(Directory.Exists(destination))Directory.Move(destination,backup);
                    try{Directory.Move(stage,destination);}catch{if(Directory.Exists(backup)&&!Directory.Exists(destination))Directory.Move(backup,destination);throw;}
                });
                var exe=Path.Combine(destination,"OfflineCaptions.exe");
                // A per-user Start menu shortcut; no registry edits or elevation.
                try {var type=Type.GetTypeFromProgID("WScript.Shell");if(type is not null){dynamic shell=Activator.CreateInstance(type)!;dynamic shortcut=shell.CreateShortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),"離線即時字幕.lnk"));shortcut.TargetPath=exe;shortcut.WorkingDirectory=destination;shortcut.Save();}}catch{}
                status.Text="安裝完成。已內附 SenseVoice Small INT8 與英翻中模型。";install.Content="安裝完成";
                Process.Start(new ProcessStartInfo(exe){UseShellExecute=true});installing=false;window.Close();
            }catch(Exception e){status.Text="安裝失敗："+e.Message;install.IsEnabled=true;installing=false;}
            finally{progress.IsIndeterminate=false;}
        };
        return app.Run(window);
    }
}
