using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
namespace OfflineCaptions;
public partial class OverlayWindow : Window {
    public bool ClickThrough {get;private set;}
    public OverlayWindow(){InitializeComponent();SourceInitialized+=(_,_)=>ApplyMouse();}
    private void DragCaption(object sender,MouseButtonEventArgs e){if(!ClickThrough&&e.LeftButton==MouseButtonState.Pressed)DragMove();}
    public void SetText(string text,bool draft=false){Caption.Text=string.IsNullOrWhiteSpace(text)?"…":text;Caption.Foreground=draft?new SolidColorBrush(Color.FromRgb(211,221,231)):Brushes.White;}
    public void Configure(double font,double opacity,double width){Caption.FontSize=font;Caption.MaxHeight=font*2.9;Panel.Background=new SolidColorBrush(Color.FromArgb((byte)(opacity*255),17,24,32));Width=width;Height=font*2.9+58;}
    public void MoveTo(Display display){
        var dpi=VisualTreeHelper.GetDpi(this);var width=Math.Min(Width*dpi.DpiScaleX,display.Width-40);var height=Height*dpi.DpiScaleY;
        Native.SetWindowPos(new WindowInteropHelper(this).Handle,new IntPtr(-1),(int)(display.Left+(display.Width-width)/2),(int)(display.Top+display.Height-height-48),(int)width,(int)height,0x10);
    }
    public void ToggleMouse(){ClickThrough=!ClickThrough;ApplyMouse();}
    private void ApplyMouse(){var hwnd=new WindowInteropHelper(this).Handle;if(hwnd==IntPtr.Zero)return;var flags=Native.GetWindowLongPtr(hwnd,-20).ToInt64();flags=ClickThrough?flags|0x20L|0x08000000L:flags&~(0x20L|0x08000000L);Native.SetWindowLongPtr(hwnd,-20,new IntPtr(flags));Hint.Text=ClickThrough?"滑鼠穿透中 · Ctrl+Alt+S 恢復拖曳":"離線字幕 · 拖曳移動 · Ctrl+Alt+S 切換滑鼠穿透";}
}
