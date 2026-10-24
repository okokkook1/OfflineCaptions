using System.Globalization;
using System.Text;
namespace OfflineCaptions;
public sealed record CaptionEntry(long Id,double Start,double End,string Original,string Text,string Language) {
    public string Time => $"{TimeSpan.FromSeconds(Start):hh\\:mm\\:ss} → {TimeSpan.FromSeconds(End):hh\\:mm\\:ss}";
}
public static class CaptionExport {
    public static string Timestamp(double seconds){var ms=Math.Max(0,(long)Math.Round(seconds*1000));return $"{ms/3600000:00}:{ms/60000%60:00}:{ms/1000%60:00},{ms%1000:000}";}
    public static string Srt(IEnumerable<CaptionEntry> entries){
        var b=new StringBuilder();int n=0;double previousEnd=0;
        foreach(var e in entries.OrderBy(x=>x.Start).ThenBy(x=>x.Id)){if(string.IsNullOrWhiteSpace(e.Text))continue;var start=Math.Max(previousEnd,e.Start);var end=Math.Max(start+0.001,e.End);b.AppendLine((++n).ToString(CultureInfo.InvariantCulture)).AppendLine($"{Timestamp(start)} --> {Timestamp(end)}").AppendLine(e.Text.Replace("\r","").Replace("\n"," ")).AppendLine();previousEnd=end;}
        return b.ToString();
    }
    public static string Txt(IEnumerable<CaptionEntry> entries)=>string.Join(Environment.NewLine+Environment.NewLine,entries.OrderBy(e=>e.Start).Select(e=>$"[{e.Time}] {e.Text}"));
}
