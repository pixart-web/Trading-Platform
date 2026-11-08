package pt.pocketalpha

import androidx.room.withTransaction
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test
import pt.pocketalpha.local.*
import pt.pocketalpha.workspace.PortableBackup
import java.util.UUID

class PortableLedgerAndroidTest {
    @Test fun encryptedRestoreIsIndependentAndAtomic() = runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val root = Json.parseToJsonElement(instrumentation.context.assets.open("local-kernel-golden.json").bufferedReader().use { it.readText() }).jsonObject
        val policy = Json.decodeFromJsonElement<LocalPolicy>(root.getValue("policy"))
        val db = LocalFinancialDatabase.open(instrumentation.targetContext)
        try {
            val ledger = LocalPaperLedger(db)
            val original = ledger.create(UUID.randomUUID().toString(),"1000",root.getValue("start").jsonPrimitive.content,policy)
            val command = Json.decodeFromJsonElement<PaperCommand>(root.getValue("commands").jsonArray.first())
            val expected = ledger.submit(original.id,0,command)
            val text = ledger.portable(original.id)
            val password = "disposable-restore-test-password" // pragma: allowlist secret; test fixture
            val bytes = PortableBackup.encrypt(text,password)
            val restored = ledger.importPortable(PortableBackup.decrypt(bytes,password))
            assertNotEquals(original.id,restored.id)
            assertEquals(expected.book,restored.book)
            val count = ledger.accounts().size
            try { ledger.importPortable(text,allowSynthetic=false); fail("synthetic journal entered operational mode") } catch (_: IllegalArgumentException) { }
            val bad = Json.parseToJsonElement(text).jsonObject.toMutableMap().apply { put("head",JsonPrimitive("0".repeat(64))) }
            try { ledger.importPortable(JsonObject(bad).toString()); fail("modified journal accepted") } catch (_: IllegalArgumentException) { }
            assertEquals(count,ledger.accounts().size)
            try { db.withTransaction { ledger.importPortable(text); throw CancellationException("interrupted before commit") } } catch (_: CancellationException) { }
            assertEquals(count,ledger.accounts().size)
            assertEquals(expected.book,ledger.restore(original.id).book)
        } finally { db.close() }
    }
}
