package e4;
import org.apache.flink.api.common.functions.MapFunction;
import java.util.concurrent.locks.LockSupport;
/** Open-loop arrivals: request idx is scheduled at base + idx/rate; a backlog (e.g. after a restart) is released at once. rate<=0: unthrottled. */
public class Pacer implements MapFunction<Long, Req> {
    final long base; final double rate;
    public Pacer(long base, double rate) { this.base = base; this.rate = rate; }
    @Override public Req map(Long idx) {
        if (rate <= 0) return new Req(idx, Util.nowNs());
        long t = base + (long) (idx * 1e9 / rate);
        long now;
        while ((now = Util.nowNs()) < t) LockSupport.parkNanos(t - now);
        return new Req(idx, t);
    }
}
