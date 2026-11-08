package pt.pocketalpha

import androidx.compose.ui.test.*
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import pt.pocketalpha.workspace.*
import pt.pocketalpha.local.*
import java.time.Instant
import java.util.UUID

class PublicWorkspaceAndroidTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    @Test fun productionLaunchIsLocalWithoutServerCredentials() {
        compose.waitUntil(15000) { compose.onAllNodesWithText("Local workspace").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithText("Local workspace").assertExists()
        compose.onNodeWithText("HTTPS server origin").assertDoesNotExist()
        compose.onNodeWithText("Private tablet storage · no Pocket Alpha server · real-money execution disabled").assertExists()
        if (InstrumentationRegistry.getArguments().getString("realProvider") == "true") {
            compose.waitUntil(30000) { compose.onAllNodesWithText("Provider response verified").fetchSemanticsNodes().isNotEmpty() }
            compose.activity.runOnUiThread { compose.activity.window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE) }
            compose.waitForIdle()
            val image = compose.onRoot().captureToImage().asAndroidBitmap()
            val directory = java.io.File(compose.activity.getExternalFilesDir(null),"screenshots").apply { mkdirs() }
            java.io.File(directory,"local-real-market.png").outputStream().use { image.compress(android.graphics.Bitmap.CompressFormat.PNG,100,it) }
            compose.onNodeWithTag("local-workspace-grid").performScrollToNode(hasText("Create new PAPER experiment"))
            compose.onNodeWithText("Create new PAPER experiment").performClick()
            compose.waitUntil(15000) { compose.onAllNodesWithText("Authoritative local account",substring=true).fetchSemanticsNodes().isNotEmpty() }
        }
    }
}
class RealPublicProviderAndroidTest {
    @Test fun actualMarketObservationsLocalIndicatorAndPortableAccount() = runBlocking {
        require(InstrumentationRegistry.getArguments().getString("realProvider") == "true") { "Explicit real-provider qualification required" }
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val provider = PublicMarkets(context)
        val market = provider.discover().first { it.id == "BTC-EUR" }
        val candles = provider.refresh(market.id)
        assertTrue(candles.size >= 20)
        assertTrue(candles.none { it.synthetic })
        val features = LocalIndicators.calculate(candles.map { CausalClose(it.close,it.close_time,it.received_at) },20,"SMA",Instant.now().toString())
        assertEquals("READY",features.last().status)
        val db = LocalFinancialDatabase.open(context)
        try {
            val ledger = LocalPaperLedger(db)
            val policy = LocalPolicy("public-device-test-1","10","10","5","5","0.05","0.01",market.step,market.step,market.minimum,"100","0.1","0.1","0.03",7200,"20",3600,false)
            val account = ledger.createPublic(UUID.randomUUID().toString(),"1000",Instant.now().toString(),policy,market.id)
            val password = "disposable-device-export-password" // pragma: allowlist secret; explicit device test
            val backup = PortableBackup.encrypt(ledger.portable(account.id),password)
            val restored = ledger.importPortable(PortableBackup.decrypt(backup,password),allowSynthetic=false)
            assertNotEquals(account.id,restored.id)
            assertEquals("1000",restored.book.cash)
            assertEquals("PUBLIC_COINBASE",ledger.accounts().first { it.id == restored.id }.origin)
            android.util.Log.i("PublicWorkspaceProof","market=${market.id} bars=${candles.size} last_close=${candles.last().close_time} source=${candles.last().source} indicator=${features.last().status} restored_cash=${restored.book.cash}")
            Unit
        } finally { db.close() }
    }
}
