using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using System.Threading.Channels;

namespace OfflineCaptions;
internal sealed class WorkerClient : IAsyncDisposable {
    private readonly NamedPipeServerStream pipe;
    private readonly Channel<object> outgoing=Channel.CreateBounded<object>(new BoundedChannelOptions(120){FullMode=BoundedChannelFullMode.Wait,SingleReader=true});
    private readonly CancellationTokenSource cancellation=new();
    private readonly TaskCompletionSource ready=new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly TaskCompletionSource stopped=new(TaskCreationOptions.RunContinuationsAsynchronously);
    private Task? writerTask,readerTask;
    private Process? process;
    private bool stopping;
    public event Action<JsonElement>? Event;
    public event Action<string>? Failure;
    public string LastError {get;private set;}="";
    private readonly string pipeName = "OfflineCaptions-"+Guid.NewGuid().ToString("N");
    public WorkerClient(){pipe=new NamedPipeServerStream(pipeName,PipeDirection.InOut,1,PipeTransmissionMode.Byte,PipeOptions.Asynchronous|PipeOptions.CurrentUserOnly);}
    public static string Root => AppContext.BaseDirectory;
    public static string Models => Environment.GetEnvironmentVariable("OFFLINE_CAPTIONS_MODELS") ?? (Directory.Exists(Path.Combine(Root,"models"))?Path.Combine(Root,"models"):Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"OfflineCaptions","models"));
    public static string Python {
        get {
            var custom=Environment.GetEnvironmentVariable("OFFLINE_CAPTIONS_PYTHON");if(!string.IsNullOrWhiteSpace(custom)&&File.Exists(custom))return custom;
            foreach(var candidate in new[]{Path.Combine(Root,"runtime","python.exe"),Path.GetFullPath(Path.Combine(Root,"..","..","..","..",".venv","Scripts","python.exe"))})if(File.Exists(candidate))return candidate;
            throw new FileNotFoundException("缺少 Python 執行環境。請使用完整安裝包，或設定 OFFLINE_CAPTIONS_PYTHON。" );
        }
    }
    public static ProcessStartInfo PythonCommand(string script, params string[] arguments){
        var info=new ProcessStartInfo(Python){UseShellExecute=false,CreateNoWindow=true,RedirectStandardError=true,RedirectStandardOutput=true,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8,WorkingDirectory=Root};
        info.ArgumentList.Add("-u");info.ArgumentList.Add(Path.Combine(Root,"backend",script));
        foreach(var a in arguments)info.ArgumentList.Add(a);
        info.Environment["PYTHONUTF8"]="1";info.Environment["HF_HUB_DISABLE_TELEMETRY"]="1";return info;
    }
    public async Task StartAsync(string language){
        var connect=pipe.WaitForConnectionAsync(cancellation.Token);
        var info=PythonCommand("worker.py","--pipe",pipeName,"--models",Models,"--language",language);
        process=Process.Start(info)??throw new IOException("無法啟動辨識程序");
        process.ErrorDataReceived+=(_,e)=>{if(e.Data is not null)LastError=e.Data;};process.BeginErrorReadLine();
        process.OutputDataReceived+=(_,_)=>{};process.BeginOutputReadLine();
        process.EnableRaisingEvents=true;process.Exited+=(_,_)=>{if(!stopping){var msg="辨識程序已結束。"+LastError;ready.TrySetException(new IOException(msg));Failure?.Invoke(msg);}};
        var connection=connect.WaitAsync(TimeSpan.FromSeconds(30));
        var first=await Task.WhenAny(connection,ready.Task);
        if(first==ready.Task)await ready.Task;
        try {await connection;}catch(Exception ex){throw new IOException("辨識程序未連上本機管道。"+LastError,ex);}
        writerTask=WriteLoop();readerTask=ReadLoop();
        await ready.Task.WaitAsync(TimeSpan.FromMinutes(3));
    }
    private async Task WriteLoop(){
        try {using var writer=new StreamWriter(pipe,new UTF8Encoding(false),65536,true){AutoFlush=true};
            await foreach(var value in outgoing.Reader.ReadAllAsync(cancellation.Token))await writer.WriteLineAsync(JsonSerializer.Serialize(value));
        }catch(Exception e) when(e is IOException or OperationCanceledException or ObjectDisposedException){if(!stopping)Failure?.Invoke("音訊管道中斷："+e.Message);}
    }
    private async Task ReadLoop(){
        try {using var reader=new StreamReader(pipe,Encoding.UTF8,false,65536,true);
            while(!cancellation.IsCancellationRequested){var line=await reader.ReadLineAsync(cancellation.Token);if(line is null)break;
                using var doc=JsonDocument.Parse(line);var ev=doc.RootElement.Clone();var type=ev.GetProperty("type").GetString();
                if(type=="ready"){
                    if(!ev.TryGetProperty("engine",out var engine)||engine.GetString()!="sensevoice")throw new IOException("背景程序版本不相符，請完整更新 SenseVoice 版本。");
                    ready.TrySetResult();
                }
                if(type=="stopped")stopped.TrySetResult();
                if(type=="error"){var msg=ev.GetProperty("message").GetString()??"辨識錯誤";ready.TrySetException(new IOException(msg));Failure?.Invoke(msg);}
                Event?.Invoke(ev);
            }
            if(!stopping&&!stopped.Task.IsCompleted)Failure?.Invoke("辨識連線已中斷，請重新開始。");
        }catch(Exception e) when(e is IOException or JsonException or OperationCanceledException or ObjectDisposedException){ready.TrySetException(e);if(!stopping)Failure?.Invoke(e.Message);}
    }
    public bool Audio(byte[] pcm,double start,uint source) => outgoing.Writer.TryWrite(new {type="audio",pcm=Convert.ToBase64String(pcm),start,source});
    public async Task Command(string type){try {await outgoing.Writer.WriteAsync(new{type},cancellation.Token);}catch(Exception e) when(e is ChannelClosedException or OperationCanceledException){if(!stopping)Failure?.Invoke("辨識程序已停止："+e.Message);}}
    public async Task StopAsync(){if(stopping)return;stopping=true;
        try {if(pipe.IsConnected){await Command("stop");await stopped.Task.WaitAsync(TimeSpan.FromSeconds(35));}}catch{}
        await DisposeAsync();
    }
    public async ValueTask DisposeAsync(){
        stopping=true;cancellation.Cancel();outgoing.Writer.TryComplete();pipe.Dispose();
        if(process is not null){try {if(!process.HasExited)process.Kill(true);}catch{}process.Dispose();process=null;}
        try {await Task.WhenAll(writerTask??Task.CompletedTask,readerTask??Task.CompletedTask).WaitAsync(TimeSpan.FromSeconds(2));}catch{}
    }
}
