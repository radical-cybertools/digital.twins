package e4;
import java.time.Instant;
public final class Util {
    private Util() {}
    /** Wall-clock epoch nanoseconds (microsecond resolution on Linux); comparable across JVMs on this host. */
    public static long nowNs() { Instant i = Instant.now(); return i.getEpochSecond() * 1_000_000_000L + i.getNano(); }
    public static void spinUs(long us) { if (us <= 0) return; long end = System.nanoTime() + us * 1000L; while (System.nanoTime() < end) { Thread.onSpinWait(); } }
    public static String arg(String[] a, String k, String d) { for (int i = 0; i + 1 < a.length; i++) if (a[i].equals("--" + k)) return a[i + 1]; return d; }
    public static double feature(long seq, int i) { return ((seq * 31 + i) % 97) / 97.0; }
}
