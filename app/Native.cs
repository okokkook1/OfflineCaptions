using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace OfflineCaptions;
public sealed record AudioSource(uint Pid, string Name, string Path, double Peak) {
    public string Label => $"{Name}  ·  PID {Pid}";
    public ImageSource? Icon { get; init; }
    public double Level => Math.Min(100, Peak * 100);
}
public sealed record AudioDevice(string Id, string Name);
public sealed record Display(string Name, double Left, double Top, double Width, double Height) {
    public override string ToString() => Name;
}
internal static class Native {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] internal delegate void CaptureCallback(int kind, IntPtr data, int count, double start, int error, IntPtr context);
    [DllImport("OfflineCapture", CallingConvention=CallingConvention.Cdecl)] internal static extern IntPtr oc_sources();
    [DllImport("OfflineCapture", CallingConvention=CallingConvention.Cdecl)] internal static extern IntPtr oc_devices();
    [DllImport("OfflineCapture", CallingConvention=CallingConvention.Cdecl)] internal static extern void oc_free(IntPtr p);
    [DllImport("OfflineCapture", CallingConvention=CallingConvention.Cdecl, CharSet=CharSet.Unicode)] internal static extern IntPtr oc_start(uint pid, string? device, CaptureCallback cb, IntPtr context);
    [DllImport("OfflineCapture", CallingConvention=CallingConvention.Cdecl)] internal static extern void oc_stop(IntPtr capture);
    [DllImport("OfflineCapture", CallingConvention=CallingConvention.Cdecl)] internal static extern void oc_pause(IntPtr capture, int paused);
    [DllImport("user32")] internal static extern bool RegisterHotKey(IntPtr hwnd, int id, uint modifiers, uint key);
    [DllImport("user32")] internal static extern bool UnregisterHotKey(IntPtr hwnd, int id);
    [DllImport("user32", EntryPoint="GetWindowLongPtrW")] internal static extern IntPtr GetWindowLongPtr(IntPtr hwnd,int index);
    [DllImport("user32", EntryPoint="SetWindowLongPtrW")] internal static extern IntPtr SetWindowLongPtr(IntPtr hwnd,int index,IntPtr value);
    [DllImport("user32")] static extern bool DestroyIcon(IntPtr icon);
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct FileInfo {
        public IntPtr Icon; public int Index; public uint Attributes;
        [MarshalAs(UnmanagedType.ByValTStr,SizeConst=260)] public string DisplayName;
        [MarshalAs(UnmanagedType.ByValTStr,SizeConst=80)] public string TypeName;
    }
    [DllImport("shell32", CharSet=CharSet.Unicode)] static extern IntPtr SHGetFileInfo(string path,uint attributes,out FileInfo info,uint size,uint flags);
    static string Json(Func<IntPtr> get) { var p=get();try{return Marshal.PtrToStringUni(p)??"[]";}finally{oc_free(p);} }
    static readonly JsonSerializerOptions Options = new(){PropertyNameCaseInsensitive=true};
    public static AudioSource[] Sources() => (JsonSerializer.Deserialize<AudioSource[]>(Json(oc_sources),Options)??[]).Select(x=>x with {Icon=GetIcon(x.Path)}).OrderBy(x=>x.Name).ToArray();
    public static AudioDevice[] Devices() => JsonSerializer.Deserialize<AudioDevice[]>(Json(oc_devices),Options)??[];
    static ImageSource? GetIcon(string path) {
        try { SHGetFileInfo(path,0,out var info,(uint)Marshal.SizeOf<FileInfo>(),0x100|1);
            if(info.Icon==IntPtr.Zero)return null;
            try {var icon=Imaging.CreateBitmapSourceFromHIcon(info.Icon,Int32Rect.Empty,BitmapSizeOptions.FromEmptyOptions());icon.Freeze();return icon;}finally{DestroyIcon(info.Icon);}
        }catch{return null;}
    }
    [StructLayout(LayoutKind.Sequential)] struct Rect {public int Left,Top,Right,Bottom;}
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct MonitorInfo {public int Size;public Rect Monitor,Work;public uint Flags;[MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)]public string Device;}
    delegate bool MonitorCallback(IntPtr monitor,IntPtr hdc,ref Rect rect,IntPtr data);
    [DllImport("user32")] static extern bool EnumDisplayMonitors(IntPtr hdc,IntPtr clip,MonitorCallback callback,IntPtr data);
    [DllImport("user32",CharSet=CharSet.Unicode)] static extern bool GetMonitorInfo(IntPtr monitor,ref MonitorInfo info);
    [DllImport("user32")] internal static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x,int y,int cx,int cy,uint flags);
    public static Display[] Displays() {
        var result=new List<Display>();
        MonitorCallback callback=(IntPtr h,IntPtr dc,ref Rect r,IntPtr data)=>{var info=new MonitorInfo{Size=Marshal.SizeOf<MonitorInfo>(),Device=""};if(GetMonitorInfo(h,ref info))result.Add(new Display($"螢幕 {result.Count+1} · {info.Device}",info.Work.Left,info.Work.Top,info.Work.Right-info.Work.Left,info.Work.Bottom-info.Work.Top));return true;};
        EnumDisplayMonitors(IntPtr.Zero,IntPtr.Zero,callback,IntPtr.Zero);return result.ToArray();
    }
    public static string CaptureError(int hr) => unchecked((uint)hr) switch {
        0x8007042B => "來源已關閉，請重新選擇軟體。",
        0x88890004 => "播放裝置已中斷或切換，請停止後重新選擇裝置。",
        0x80070005 => "無法存取來源音訊，請確認來源軟體的權限。",
        _ => $"無法擷取音訊（0x{unchecked((uint)hr):X8}），可手動改選整個播放裝置。"
    };
}
