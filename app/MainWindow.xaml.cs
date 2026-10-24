using Microsoft.Win32;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Threading;

namespace OfflineCaptions;
public partial class MainWindow : Window {
    readonly ObservableCollection<CaptionEntry> history=[];
    readonly OverlayWindow overlay=new();
    readonly DispatcherTimer heartbeat=new(){Interval=TimeSpan.FromSeconds(1)};
    readonly DispatcherTimer refreshTimer=new(){Interval=TimeSpan.FromSeconds(2)};
    WorkerClient? worker;
    Native.CaptureCallback? callback;
    IntPtr capture;
    HwndSource? hwndSource;
    bool active,paused,starting,stopping,closing,modelBusy;
    bool hotkeyMouse;
    bool benchmark;
    readonly List<double> benchmarkRtfs=[];
    DateTime benchmarkEnd;
    readonly Stopwatch clock=new();
    double lastInput, lastPacketAt;
    double inputLevel;
    long displayedId=-1;
    double displayedAt;
    long transportDrops;
    uint sourcePid;
    private string SourceLanguage => (LanguagePicker.SelectedItem as ComboBoxItem)?.Tag?.ToString()??"auto";
    public MainWindow(){
        InitializeComponent();History.ItemsSource=history;
        Loaded+=OnLoaded;Closing+=OnClosing;
        heartbeat.Tick+=OnHeartbeat;refreshTimer.Tick+=async(_,_)=>{if(!active&&!starting&&!closing)await RefreshSources();};
        SystemEvents.PowerModeChanged+=PowerChanged;
    }
    async void OnLoaded(object sender,RoutedEventArgs e){
        hwndSource=HwndSource.FromHwnd(new WindowInteropHelper(this).Handle);hwndSource?.AddHook(WindowHook);
        var hwnd=new WindowInteropHelper(this).Handle;
        hotkeyMouse=Native.RegisterHotKey(hwnd,1,0x4000|0x0001|0x0002,0x53);
        var hideKey=Native.RegisterHotKey(hwnd,2,0x4000|0x0001|0x0002,0x48);
        if(!hotkeyMouse||!hideKey){HotkeyHint.Text="快捷鍵被其他程式占用；可用此面板控制字幕。";MouseButton.IsEnabled=hotkeyMouse;}
        Screens.ItemsSource=Native.Displays();Screens.SelectedIndex=0;
        await RefreshSources();refreshTimer.Start();heartbeat.Start();
        if(Environment.GetCommandLineArgs().Contains("--self-test"))await SelfTest();
        var arguments=Environment.GetCommandLineArgs();var pipeline=Array.IndexOf(arguments,"--pipeline-test");
        if(pipeline>=0&&arguments.Length>pipeline+1)await PipelineTest(arguments[pipeline+1]);
        var captureTest=Array.IndexOf(arguments,"--capture-test");
        if(captureTest>=0&&arguments.Length>captureTest+1)await CaptureTest(arguments[captureTest+1]);
    }
    IntPtr WindowHook(IntPtr hwnd,int msg,IntPtr wParam,IntPtr lParam,ref bool handled){
        if(msg==0x0312){if(wParam.ToInt32()==1)ToggleMouse();else if(wParam.ToInt32()==2)ToggleOverlay();handled=true;}return IntPtr.Zero;
    }
    async Task RefreshSources(){
        try {
            var selected=(Sources.SelectedItem as AudioSource)?.Pid;
            var selectedDevice=(Devices.SelectedItem as AudioDevice)?.Id;
            var result=await Task.Run(()=>(Native.Sources(),Native.Devices()));
            if(closing)return;
            Sources.ItemsSource=result.Item1;Sources.SelectedItem=result.Item1.FirstOrDefault(x=>x.Pid==selected)??result.Item1.FirstOrDefault();
            Devices.ItemsSource=result.Item2;Devices.SelectedItem=result.Item2.FirstOrDefault(x=>x.Id==selectedDevice)??result.Item2.FirstOrDefault();
        }catch(Exception ex){SetStatus("無法列出聲音來源",ex.Message);}
    }
    async void RefreshClick(object sender,RoutedEventArgs e)=>await RefreshSources();
    void CaptureModeChanged(object sender,SelectionChangedEventArgs e){if(Sources is null)return;bool app=CaptureMode.SelectedIndex==0;Sources.Visibility=app?Visibility.Visible:Visibility.Collapsed;Devices.Visibility=app?Visibility.Collapsed:Visibility.Visible;SourceLabel.Text=app?"應用程式":"播放裝置";}
    async void StartClick(object sender,RoutedEventArgs e)=>await StartSession(false);
    async Task StartSession(bool test){
        if(active||starting||modelBusy||stopping)return;
        uint pid=0;string? device=null;
        if(CaptureMode.SelectedIndex==0){if(Sources.SelectedItem is not AudioSource source){SetStatus("請先選擇來源","先讓會議或播放器發出聲音，再按重新整理。");return;}pid=source.Pid;}
        else {if(Devices.SelectedItem is not AudioDevice selected){SetStatus("找不到播放裝置","請先連接耳機或喇叭。");return;}device=selected.Id;}
        foreach(var file in new[]{Path.Combine(WorkerClient.Models,"sensevoice-small-int8","model.int8.onnx"),Path.Combine(WorkerClient.Models,"sensevoice-small-int8","tokens.txt"),Path.Combine(WorkerClient.Models,"opus-en-zh","model.bin")}){
            if(!File.Exists(file)){SetStatus("缺少離線模型","請展開「模型管理與效能測試」，下載或匯入模型包。");return;}
        }
        starting=true;benchmark=test;benchmarkRtfs.Clear();SetButtons();
        SetStatus("載入離線模型…","首次載入可能需要一些時間；尚未開始收音。");
        try {
            worker=new WorkerClient();var current=worker;
            worker.Event+=ev=>Dispatcher.BeginInvoke(()=>{if(ReferenceEquals(worker,current))HandleEvent(ev);});
            worker.Failure+=message=>Dispatcher.BeginInvoke(async()=>{if(ReferenceEquals(worker,current)&&!stopping){SetStatus("字幕已中斷",message);await StopSession(true);}});
            await worker.StartAsync(SourceLanguage);
            if(closing)throw new OperationCanceledException("程式正在關閉");
            sourcePid=pid;clock.Restart();lastInput=0;lastPacketAt=0;transportDrops=0;displayedId=-1;
            var ready=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            callback=(kind,data,count,start,error,context)=>{
                if(kind==2){ready.TrySetResult();return;}
                if(kind==1){var msg=Native.CaptureError(error);ready.TrySetException(new IOException(msg));Dispatcher.BeginInvoke(async()=>{if(!starting&&!stopping&&active){SetStatus("收音已中斷",msg);await StopSession(true);}});return;}
                if(kind!=0||count<=0)return;
                Volatile.Write(ref lastPacketAt,clock.Elapsed.TotalSeconds);
                var bytes=new byte[count];Marshal.Copy(data,bytes,0,count);
                double peak=0;for(int i=0;i+1<bytes.Length;i+=2){var s=BitConverter.ToInt16(bytes,i)/32768.0;peak=Math.Max(peak,Math.Abs(s));}
                Volatile.Write(ref inputLevel,peak);if(peak>0.003)Volatile.Write(ref lastInput,clock.Elapsed.TotalSeconds);
                var w=worker;if(w is not null&&!w.Audio(bytes,start,sourcePid))Interlocked.Increment(ref transportDrops);
            };
            capture=Native.oc_start(pid,device,callback,IntPtr.Zero);
            if(capture==IntPtr.Zero)throw new IOException("無法建立收音工作");
            await ready.Task.WaitAsync(TimeSpan.FromSeconds(20));
            // A new session has its own time origin. Preserve past history until start succeeds.
            history.Clear();CountLabel.Text="0 段";active=true;paused=false;
            ShowOverlay();overlay.SetText(test?"效能測試中，請讓來源持續播放語音…":"正在聆聽…");
            benchmarkEnd=DateTime.UtcNow.AddSeconds(10);
            SetStatus(test?"10 秒效能測試中":"正在產生繁中字幕",test?"請讓所選來源持續播放中英文語音；測試結束會自動停止。":"音訊及字幕不會自動寫入檔案。");
        }catch(Exception ex){SetStatus("無法開始字幕",ex.Message);await StopSession(true);}
        finally{starting=false;SetButtons();}
    }
    void HandleEvent(JsonElement ev){
        var type=ev.GetProperty("type").GetString();
        if(type=="ready")ModelStatus.Text=ev.GetProperty("model").GetString()+" · CPU";
        if(type=="caption"){
            long id=ev.GetProperty("id").GetInt64();bool final=ev.GetProperty("final").GetBoolean();
            var text=ev.GetProperty("text").GetString()??"";
            double rtf=ev.GetProperty("rtf").GetDouble(),latency=ev.GetProperty("latency").GetDouble();
            latency=Math.Max(latency,clock.Elapsed.TotalSeconds-ev.GetProperty("end").GetDouble());
            Metrics.Text=$"收音 {inputLevel*100:F0}%　處理延遲 {latency:F1} 秒　速度比 {rtf:F2}";
            if(benchmark&&final)benchmarkRtfs.Add(rtf);
            if(rtf>1.0)Detail.Text="處理速度不足；請關閉其他耗能程式。";
            if(final&&!string.IsNullOrWhiteSpace(text)&&!history.Any(x=>x.Id==id)){
                var entry=new CaptionEntry(id,ev.GetProperty("start").GetDouble(),ev.GetProperty("end").GetDouble(),ev.GetProperty("original").GetString()??"",text,ev.GetProperty("language").GetString()??"");
                history.Add(entry);History.ScrollIntoView(entry);CountLabel.Text=$"{history.Count} 段";
            }
            if(id>=displayedId){displayedId=id;displayedAt=clock.Elapsed.TotalSeconds;overlay.SetText(text,!final);}
        }else if(type=="dropped"){
            Detail.Text=ev.GetProperty("message").GetString();
            var id=ev.GetProperty("id").GetInt64();if(id==displayedId)overlay.SetText("已略過延遲片段，繼續聆聽…");
        }
    }
    async void PauseClick(object sender,RoutedEventArgs e){
        if(!active||worker is null||stopping)return;paused=!paused;
        Native.oc_pause(capture,paused?1:0);
        if(paused)await worker.Command("pause");
        else {lastInput=clock.Elapsed.TotalSeconds;SetStatus("正在產生繁中字幕","已恢復收音。");}
        PauseButton.Content=paused?"繼續":"暫停";
        if(paused){SetStatus("已暫停","暫停期間的音訊不會送入辨識；現有片段會完成處理。");overlay.SetText("已暫停");}
    }
    async void StopClick(object sender,RoutedEventArgs e)=>await StopSession(false);
    async Task StopSession(bool preserveStatus){
        if(stopping)return;stopping=true;SetButtons();
        try {
            var h=capture;capture=IntPtr.Zero;if(h!=IntPtr.Zero)await Task.Run(()=>Native.oc_stop(h));
            callback=null;
            if(worker is not null){var w=worker;await w.StopAsync();worker=null;}
            active=false;paused=false;clock.Stop();InputLevel.Value=0;PauseButton.Content="暫停";
            if(!preserveStatus){SetStatus("已結束",$"共 {history.Count} 段完成字幕。可匯出 TXT 或 SRT。");overlay.SetText("本次字幕已結束");}
        }finally{stopping=false;SetButtons();}
    }
    void SetButtons(){if(StartButton is null)return;bool busy=active||starting||stopping||modelBusy;StartButton.IsEnabled=!busy;PauseButton.IsEnabled=active&&!stopping&&!starting;StopButton.IsEnabled=active&&!stopping&&!starting;Sources.IsEnabled=!busy;Devices.IsEnabled=!busy;CaptureMode.IsEnabled=!busy;LanguagePicker.IsEnabled=!busy;}
    void SetStatus(string status,string detail){Status.Text=status;Detail.Text=detail;}
    async void OnHeartbeat(object? sender,EventArgs e){
        if(!active||paused||starting||stopping)return;
        var now=clock.Elapsed.TotalSeconds;
        InputLevel.Value=now-Volatile.Read(ref lastPacketAt)>0.5?0:Volatile.Read(ref inputLevel)*100;
        if(now-Volatile.Read(ref lastPacketAt)>0.7&&worker is not null)await worker.Command("idle");
        if(Interlocked.Exchange(ref transportDrops,0)>0)Detail.Text="音訊處理落後，部分片段未送入辨識；請關閉其他耗能程式。";
        if(now-Volatile.Read(ref lastInput)>8)Detail.Text="未收到聲音；請確認來源仍在播放，並檢查選定的應用程式。";
        else if(Detail.Text.StartsWith("未收到聲音"))Detail.Text="已收到聲音，正在產生字幕。";
        if(now-displayedAt>12&&!string.IsNullOrWhiteSpace(overlay.Caption.Text))overlay.SetText("正在聆聽…");
        if(benchmark&&DateTime.UtcNow>=benchmarkEnd){
            await StopSession(false);benchmark=false;
            if(benchmarkRtfs.Count==0)SetStatus("效能測試無有效語音","未辨識到完整語句，請讓來源播放語音後重試。");
            else {var avg=benchmarkRtfs.Average();SetStatus(avg<1?"測試完成：能跟上音訊":"測試完成：目前處理較慢",$"辨識 {benchmarkRtfs.Count} 段，平均處理速度比 {avg:F2}（低於 1 表示處理快於語音長度）。此為短測試，仍需長時間實測。");}
        }
    }
    void ShowOverlay(){if(!overlay.IsVisible)overlay.Show();ConfigureOverlay();if(Screens.SelectedItem is Display d)overlay.MoveTo(d);}
    void ConfigureOverlay(){if(FontSlider is null||OpacitySlider is null||WidthSlider is null)return;overlay.Configure(FontSlider.Value,OpacitySlider.Value,WidthSlider.Value);}
    void AppearanceChanged(object sender,RoutedPropertyChangedEventArgs<double> e){if(overlay is not null)ConfigureOverlay();}
    void ScreenChanged(object sender,SelectionChangedEventArgs e){if(overlay.IsVisible&&Screens.SelectedItem is Display d)overlay.MoveTo(d);}
    void PreviewClick(object sender,RoutedEventArgs e){ShowOverlay();if(!active)overlay.SetText("讓每一句話，都有清楚的繁體中文字幕。");}
    void ToggleOverlay(){if(overlay.IsVisible)overlay.Hide();else ShowOverlay();}
    void ToggleMouse(){if(!hotkeyMouse)return;ShowOverlay();overlay.ToggleMouse();MouseButton.Content=overlay.ClickThrough?"恢復滑鼠操作":"滑鼠穿透";}
    void MouseClick(object sender,RoutedEventArgs e)=>ToggleMouse();
    void ExportTxtClick(object sender,RoutedEventArgs e)=>Export(false);
    void ExportSrtClick(object sender,RoutedEventArgs e)=>Export(true);
    void Export(bool srt){
        if(history.Count==0){SetStatus("尚無完成字幕","先開始收音，等待一段完整語音完成辨識。");return;}
        var dialog=new SaveFileDialog{Filter=srt?"SubRip 字幕|*.srt":"文字檔|*.txt",FileName=$"字幕-{DateTime.Now:yyyyMMdd-HHmmss}.{(srt?"srt":"txt")}"};
        if(dialog.ShowDialog(this)==true)try {File.WriteAllText(dialog.FileName,srt?CaptionExport.Srt(history):CaptionExport.Txt(history),new UTF8Encoding(true));Detail.Text="字幕已匯出："+dialog.FileName;}catch(Exception ex){SetStatus("匯出失敗",ex.Message);}
    }
    async Task ManageModel(string action,string? file=null){
        if(active||starting||stopping||modelBusy){Detail.Text="請先結束字幕，再管理模型。";return;}
        modelBusy=true;SetButtons();ModelStatus.Text="處理中…";SetStatus("模型處理中",action=="download"?"正在下載與準備模型；需要網路，過程可能需要數分鐘。":"正在檢查模型包並處理檔案…");
        try {
            var args=new List<string>{action,"--root",WorkerClient.Models};if(file is not null){args.Add("--file");args.Add(file);}
            using var process=Process.Start(WorkerClient.PythonCommand("models.py",args.ToArray()))??throw new IOException("無法啟動模型工具");
            var stdout=process.StandardOutput.ReadToEndAsync();var stderr=process.StandardError.ReadToEndAsync();
            await process.WaitForExitAsync();var output=await stdout;var error=await stderr;
            if(process.ExitCode!=0)throw new IOException(error.Length>1200?error[^1200..]:error);
            ModelStatus.Text="模型準備完成";SetStatus("模型處理完成",string.IsNullOrWhiteSpace(output)?"模型包已準備完成。":output.Trim());
        }catch(Exception ex){ModelStatus.Text="模型尚未準備完成";SetStatus("模型處理失敗",ex.Message);}
        finally{modelBusy=false;SetButtons();}
    }
    async void DownloadClick(object sender,RoutedEventArgs e)=>await ManageModel("download");
    async void ImportClick(object sender,RoutedEventArgs e){var dialog=new OpenFileDialog{Filter="離線模型包|*.zip"};if(dialog.ShowDialog(this)==true)await ManageModel("import",dialog.FileName);}
    async void ExportModelsClick(object sender,RoutedEventArgs e){var dialog=new SaveFileDialog{Filter="離線模型包|*.zip",FileName="OfflineCaptions-models-sensevoice-int8.zip"};if(dialog.ShowDialog(this)==true)await ManageModel("export",dialog.FileName);}
    async void BenchmarkClick(object sender,RoutedEventArgs e)=>await StartSession(true);
    void PowerChanged(object sender,PowerModeChangedEventArgs e){if(e.Mode==PowerModes.Suspend)Dispatcher.BeginInvoke(async()=>{if(active){SetStatus("電腦進入休眠","恢復後請重新選擇聲音來源並開始。");await StopSession(true);}});}
    async void OnClosing(object? sender,CancelEventArgs e){
        if(closing)return;
        if(modelBusy){e.Cancel=true;SetStatus("模型仍在處理中","請等待下載或匯入完成，再關閉程式。");return;}
        e.Cancel=true;closing=true;heartbeat.Stop();refreshTimer.Stop();await Task.Yield();await StopSession(true);
        SystemEvents.PowerModeChanged-=PowerChanged;
        var hwnd=new WindowInteropHelper(this).Handle;Native.UnregisterHotKey(hwnd,1);Native.UnregisterHotKey(hwnd,2);hwndSource?.RemoveHook(WindowHook);overlay.Close();Close();
    }
    async Task SelfTest(){
        // Exercises real WPF construction and export, without capturing user audio.
        try {
            var samples=new[]{new CaptionEntry(1,0,1.25,"Hello","你好","en"),new CaptionEntry(2,1.25,2.5,"谢谢","謝謝","zh")};
            if(!CaptionExport.Srt(samples).Contains("00:00:01,250"))throw new Exception("SRT 時間錯誤");
            ShowOverlay();overlay.SetText("離線字幕測試成功。Hello → 你好。");overlay.ToggleMouse();overlay.ToggleMouse();
            UpdateLayout();overlay.UpdateLayout();
            var folder=Environment.GetEnvironmentVariable("OFFLINE_CAPTIONS_TEST_OUTPUT")??Path.GetTempPath();Directory.CreateDirectory(folder);
            foreach(var (visual,name) in new[]{((FrameworkElement)this,"control-panel.png"),((FrameworkElement)overlay,"overlay.png")}){
                var bitmap=new System.Windows.Media.Imaging.RenderTargetBitmap((int)visual.ActualWidth,(int)visual.ActualHeight,96,96,System.Windows.Media.PixelFormats.Pbgra32);bitmap.Render(visual);
                var encoder=new System.Windows.Media.Imaging.PngBitmapEncoder();encoder.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(bitmap));using var stream=File.Create(Path.Combine(folder,name));encoder.Save(stream);
            }
            File.WriteAllText(Path.Combine(folder,"desktop-self-test.txt"),"PASS: WPF load, native enumeration, overlay, click-through, SRT export.");
        }catch(Exception ex){File.WriteAllText(Path.Combine(Environment.GetEnvironmentVariable("OFFLINE_CAPTIONS_TEST_OUTPUT")??Path.GetTempPath(),"desktop-self-test.txt"),ex.ToString());Environment.ExitCode=1;}
        await Task.Delay(300);Close();
    }
    async Task PipelineTest(string fixture){
        var folder=Environment.GetEnvironmentVariable("OFFLINE_CAPTIONS_TEST_OUTPUT")??Path.GetTempPath();Directory.CreateDirectory(folder);
        var events=new List<JsonElement>();var sync=new object();
        try {
            byte[] pcm=[];
            using(var file=File.OpenRead(fixture))using(var reader=new BinaryReader(file)){
                if(new string(reader.ReadChars(4))!="RIFF")throw new IOException("Not WAV");reader.ReadInt32();if(new string(reader.ReadChars(4))!="WAVE")throw new IOException("Not WAVE");
                bool format=false;
                while(file.Position+8<=file.Length){var chunk=new string(reader.ReadChars(4));var size=reader.ReadInt32();var next=file.Position+size+(size%2);
                    if(chunk=="fmt "){var tag=reader.ReadInt16();var channels=reader.ReadInt16();var rate=reader.ReadInt32();reader.ReadInt32();reader.ReadInt16();var bits=reader.ReadInt16();format=tag==1&&channels==1&&rate==16000&&bits==16;}
                    if(chunk=="data")pcm=reader.ReadBytes(size);file.Position=next;
                }
                if(!format||pcm.Length==0)throw new IOException("Fixture must be mono PCM16 16kHz");
            }
            await using var client=new WorkerClient();
            string? failure=null;
            client.Event+=ev=>{lock(sync)events.Add(ev);};client.Failure+=message=>failure=message;
            await client.StartAsync("auto");clock.Restart();
            for(int offset=0;offset<pcm.Length;offset+=3200){var block=pcm.Skip(offset).Take(3200).ToArray();if(!client.Audio(block,offset/32000.0,0))throw new IOException("Audio queue full during realtime test");await Task.Delay(100);}
            await client.StopAsync();if(failure is not null)throw new IOException(failure);
            JsonElement[] captions;lock(sync)captions=events.Where(x=>x.GetProperty("type").GetString()=="caption"&&x.GetProperty("final").GetBoolean()).ToArray();
            if(captions.Length==0||!captions.Any(x=>x.GetProperty("text").GetString()?.Any(c=>c>='\u3400'&&c<='\u9fff')==true))throw new IOException("No final Chinese captions");
            if(captions.Select(x=>x.GetProperty("id").GetInt64()).Distinct().Count()!=captions.Length)throw new IOException("Duplicate final captions");
            var entries=captions.Select(x=>new CaptionEntry(x.GetProperty("id").GetInt64(),x.GetProperty("start").GetDouble(),x.GetProperty("end").GetDouble(),x.GetProperty("original").GetString()??"",x.GetProperty("text").GetString()??"",x.GetProperty("language").GetString()??"")).ToArray();
            File.WriteAllText(Path.Combine(folder,"pipeline.srt"),CaptionExport.Srt(entries),new UTF8Encoding(true));
            File.WriteAllText(Path.Combine(folder,"pipeline-test.json"),JsonSerializer.Serialize(new{status="PASS",events,captions=captions.Length},new JsonSerializerOptions{WriteIndented=true}));
        }catch(Exception ex){File.WriteAllText(Path.Combine(folder,"pipeline-test.json"),ex.ToString());Environment.ExitCode=1;}
        Close();
    }
    [DllImport("winmm.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool PlaySound(string? file,IntPtr module,uint flags);
    async Task CaptureTest(string fixture){
        var folder=Environment.GetEnvironmentVariable("OFFLINE_CAPTIONS_TEST_OUTPUT")??Path.GetTempPath();Directory.CreateDirectory(folder);
        try {
            var source=new AudioSource((uint)Environment.ProcessId,"合成測試語音",Environment.ProcessPath??"",0);
            Sources.ItemsSource=new[]{source};Sources.SelectedIndex=0;CaptureMode.SelectedIndex=0;LanguagePicker.SelectedIndex=1;
            await StartSession(false);if(!active)throw new IOException(Status.Text+" "+Detail.Text);
            if(!PlaySound(fixture,IntPtr.Zero,0x00020000|0x0001|0x0002))throw new IOException("測試語音播放失敗");
            // Fixture duration is under 10 seconds; leave time for silence-triggered finalization.
            await Task.Delay(14000);await StopSession(false);
            if(history.Count==0||!history.Any(x=>x.Original.Contains("Hello",StringComparison.OrdinalIgnoreCase)))throw new IOException("No recognized speech from real loopback capture");
            if(!history.Any(x=>x.Text.Any(c=>c>='\u3400'&&c<='\u9fff')))throw new IOException("Missing translated caption");
            File.WriteAllText(Path.Combine(folder,"capture-test.json"),JsonSerializer.Serialize(new{status="PASS",captions=history.ToArray()},new JsonSerializerOptions{WriteIndented=true}));
            File.WriteAllText(Path.Combine(folder,"capture-test.srt"),CaptionExport.Srt(history),new UTF8Encoding(true));
        }catch(Exception ex){File.WriteAllText(Path.Combine(folder,"capture-test.json"),ex.ToString());Environment.ExitCode=1;}
        finally{PlaySound(null,IntPtr.Zero,0);await StopSession(true);}
        Close();
    }
}
