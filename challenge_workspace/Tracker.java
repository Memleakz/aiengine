// Polyglot Challenge - Java
public class Tracker {
    private String traceId;

    public Tracker(String traceId) {
        this.traceId = traceId;
    }

    public void logEvent(String name) {
        System.out.println("[" + this.traceId + "] Event: " + name);
    }
}
