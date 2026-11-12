package e4;
import org.apache.flink.api.connector.sink2.Sink;
import org.apache.flink.api.connector.sink2.SinkWriter;
import org.apache.flink.api.connector.sink2.WriterInitContext;
import java.io.*;
import java.util.HashSet;
/** log: one line per answer "A,seq,gen,ver,tSched,tAns".  stats: "B,bucket100ms,count" per 100 ms,
 *  "V,ver,tAns" at the first answer per model version, "L,seq,ver,tSched,tAns" for every sampleEvery-th answer. */
public class RecSink implements Sink<Ans> {
    final String path; final boolean log; final long sampleEvery;
    public RecSink(String path, boolean log, long sampleEvery) { this.path = path; this.log = log; this.sampleEvery = sampleEvery; }
    @Override public SinkWriter<Ans> createWriter(WriterInitContext ctx) throws IOException {
        return new W(path + "-" + ctx.getTaskInfo().getIndexOfThisSubtask() + ".csv");
    }
    class W implements SinkWriter<Ans> {
        final BufferedWriter out; long bucket = -1, count = 0; long maxVer = Long.MIN_VALUE; final HashSet<Long> seen = new HashSet<>();
        W(String p) throws IOException { out = new BufferedWriter(new FileWriter(p, true), 1 << 16); }
        @Override public void write(Ans a, Context c) throws IOException {
            long t = Util.nowNs();
            if (log) { out.write("A," + a.seq + "," + a.gen + "," + a.ver + "," + a.tSched + "," + t + "\n"); out.flush(); return; }
            long b = t / 100_000_000L;
            if (b != bucket) { if (bucket >= 0) out.write("B," + bucket + "," + count + "\n"); out.flush(); bucket = b; count = 0; }
            count++;
            if (a.ver != maxVer && seen.add(a.ver)) { out.write("V," + a.ver + "," + t + "\n"); if (a.ver > maxVer) maxVer = a.ver; }
            if (a.seq % sampleEvery == 0) out.write("L," + a.seq + "," + a.ver + "," + a.tSched + "," + t + "\n");
        }
        @Override public void flush(boolean end) throws IOException { out.flush(); }
        @Override public void close() throws IOException { if (!log && bucket >= 0) out.write("B," + bucket + "," + count + "\n"); out.close(); }
    }
}
