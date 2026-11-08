package pt.pocketalpha

import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test
import pt.pocketalpha.local.*
import pt.pocketalpha.workspace.PortableBackup
import java.util.UUID
import java.security.KeyStore

/** Run last, only on a disposable emulator: intentionally destroys its financial device key. */
class KeyLossAndroidTest {
    @Test fun missingDeviceKeyDoesNotInventBalancesAndPortableBackupStillWorks() = runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val root = Json.parseToJsonElement(instrumentation.context.assets.open("local-kernel-golden.json").bufferedReader().use { it.readText() }).jsonObject
        val db = LocalFinancialDatabase.open(instrumentation.targetContext)
        try {
            val ledger = LocalPaperLedger(db)
            val account = ledger.create(UUID.randomUUID().toString(),"1000",root.getValue("start").jsonPrimitive.content,Json.decodeFromJsonElement(root.getValue("policy")))
            val password = "disposable-key-loss-password" // pragma: allowlist secret; device test
            val exported = PortableBackup.encrypt(ledger.portable(account.id),password)
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("pocket-local-financial-v1") }
            try { ledger.restore(account.id); fail("lost key produced an account") } catch (_: java.security.GeneralSecurityException) { }
            val restored = ledger.importPortable(PortableBackup.decrypt(exported,password))
            assertNotEquals(account.id,restored.id)
            assertEquals("1000",restored.book.cash)
            assertTrue(ledger.accounts().any { it.id == restored.id })
            assertTrue(ledger.unavailableAccounts.contains(account.id))
        } finally { db.close() }
    }
}
