package e4;
/** Model code version 1 (the component that is swapped). */
public final class Model {
    public static final long VERSION = 1;
    public static double apply(long seq, long workUs) {
        double y = 0; for (int i = 0; i < 16; i++) y += Math.sin(i) * Util.feature(seq, i);
        Util.spinUs(workUs); return y;
    }
}
