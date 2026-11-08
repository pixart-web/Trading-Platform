package pt.pocketalpha

import android.os.Bundle

/** Debug-only entry preserving server-client regression tests; not the production launch route. */
class LegacyClientActivity : MainActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        intent.putExtra("legacyClient", true)
        super.onCreate(savedInstanceState)
    }
}
