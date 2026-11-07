package pt.pocketalpha.runtimeproof;
import android.app.Activity;
import android.os.Bundle;
import android.os.Debug;
import android.widget.TextView;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
public class ProbeActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        long started = android.os.SystemClock.elapsedRealtime();
        if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
        String result = Python.getInstance().getModule("financial_probe").callAttr("run").toString();
        android.util.Log.i("PocketRuntimeProof", result);
        android.util.Log.i("PocketRuntimeProof", "startup_ms=" + (android.os.SystemClock.elapsedRealtime()-started) + " pss_kb=" + Debug.getPss());
        TextView view = new TextView(this); view.setText(result); setContentView(view);
        try (java.io.FileOutputStream output = openFileOutput("proof.json", MODE_PRIVATE)) {
            output.write(result.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        } catch (java.io.IOException failure) { throw new IllegalStateException(failure); }
    }
}
