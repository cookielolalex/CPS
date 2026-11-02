using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading.Tasks;

// Arrival observations are made when a stream read completes, not at CLI emission.
public static class CPS036TimedCapture {
    public static async Task Pump(Stream input, Stream output, Stream observations, Stopwatch clock) {
        byte[] buffer = new byte[16384];
        long offset = 0; long lineStart = 0;
        while (true) {
            int count = await input.ReadAsync(buffer, 0, buffer.Length).ConfigureAwait(false);
            if (count == 0) break;
            long observed = clock.ElapsedMilliseconds;
            string utc = DateTime.UtcNow.ToString("o");
            await output.WriteAsync(buffer, 0, count).ConfigureAwait(false);
            if (observations != null) {
                for (int i=0; i<count; i++) {
                    if (buffer[i] == 10) {
                        long end = offset+i+1;
                        string json = "{\"line_start\":"+lineStart+",\"line_end\":"+end+",\"observed_ms\":"+observed+",\"observed_utc\":\""+utc+"\",\"terminated\":true}\n";
                        byte[] encoded = Encoding.UTF8.GetBytes(json);
                        await observations.WriteAsync(encoded,0,encoded.Length).ConfigureAwait(false);
                        lineStart=end;
                    }
                }
            }
            offset += count;
        }
        if (observations != null && lineStart<offset) {
            string json = "{\"line_start\":"+lineStart+",\"line_end\":"+offset+",\"observed_ms\":"+clock.ElapsedMilliseconds+",\"observed_utc\":\""+DateTime.UtcNow.ToString("o")+"\",\"terminated\":false}\n";
            byte[] encoded=Encoding.UTF8.GetBytes(json);
            await observations.WriteAsync(encoded,0,encoded.Length).ConfigureAwait(false);
        }
        await output.FlushAsync().ConfigureAwait(false);
        if (observations != null) await observations.FlushAsync().ConfigureAwait(false);
    }
}
