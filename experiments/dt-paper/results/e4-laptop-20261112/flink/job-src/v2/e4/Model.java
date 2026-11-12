package e4;
/** Model code version 2 (the component that is swapped). */
public final class Model {
    public static final long VERSION = 2;
    public static double apply(long seq, long workUs) {
        double y = 0; for (int i = 0; i < 16; i++) y += Math.cos(i) * Util.feature(seq, i);
        Util.spinUs(workUs); return y;
    }
}
