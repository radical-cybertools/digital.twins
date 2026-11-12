package e4;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.functions.RichMapFunction;
import org.apache.flink.api.connector.source.lib.NumberSequenceSource;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
/** Path 1: source -> pacer -> model (code version from Model.class in this jar) -> recording sink; all chained, p=1. */
public class SwapJob {
    public static void main(String[] a) throws Exception {
        int gen = Integer.parseInt(Util.arg(a, "gen", "0"));
        long base = Long.parseLong(Util.arg(a, "base", "0"));
        double rate = Double.parseDouble(Util.arg(a, "rate", "1000"));
        long work = Long.parseLong(Util.arg(a, "work-us", "0"));
        String out = Util.arg(a, "out", "/tmp/e4");
        int p = Integer.parseInt(Util.arg(a, "p", "1"));
        int stateMb = Integer.parseInt(Util.arg(a, "state-mb", "0"));
        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.setParallelism(p); env.setBufferTimeout(0);
        env.fromSource(new NumberSequenceSource(0, Long.MAX_VALUE), WatermarkStrategy.noWatermarks(), "requests").uid("src")
           .map(new Pacer(base, rate / p)).uid("pace").name("pace")
           .map(new StatefulModel(gen, work, stateMb)).uid("model").name("model-v" + Model.VERSION)
           .sinkTo(new RecSink(out + "/ans-g" + gen, true, 1)).uid("sink").name("sink");
        env.execute("e4-swap-g" + gen + "-v" + Model.VERSION);
    }
    /** The swapped operator; optionally carries stateMb MB of operator state (the "model state") through the savepoint. */
    static class StatefulModel extends RichMapFunction<Req, Ans> implements org.apache.flink.streaming.api.checkpoint.CheckpointedFunction {
        final int gen; final long work; final int stateMb;
        transient org.apache.flink.api.common.state.ListState<byte[]> st; transient java.util.List<byte[]> blob;
        StatefulModel(int gen, long work, int stateMb) { this.gen = gen; this.work = work; this.stateMb = stateMb; }
        @Override public void initializeState(org.apache.flink.runtime.state.FunctionInitializationContext c) throws Exception {
            st = c.getOperatorStateStore().getListState(new org.apache.flink.api.common.state.ListStateDescriptor<>("blob", byte[].class));
            blob = new java.util.ArrayList<>(); for (byte[] b : st.get()) blob.add(b);
            if (blob.isEmpty()) { java.util.Random rnd = new java.util.Random(gen);
                for (int i = 0; i < stateMb; i++) { byte[] b = new byte[1 << 20]; rnd.nextBytes(b); blob.add(b); } }
        }
        @Override public void snapshotState(org.apache.flink.runtime.state.FunctionSnapshotContext c) throws Exception { st.update(blob); }
        @Override public Ans map(Req r) {
            Ans x = new Ans(); x.seq = r.seq; x.tSched = r.tSched; x.gen = gen; x.ver = Model.VERSION;
            x.y = Model.apply(r.seq, work); return x;
        }
    }
}
