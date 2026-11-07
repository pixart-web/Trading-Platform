package pt.pocketalpha

import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.Dispatchers
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test
import pt.pocketalpha.local.*

/** No Activity, backend, HTTP server or broker required; two invocations span process death. */
class LocalStandaloneEngineTest {
    @Test fun encryptedJournalReconcilesAcrossProcessRestart() = runBlocking {
        val started = android.os.SystemClock.elapsedRealtime()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val args = InstrumentationRegistry.getArguments()
        val text = instrumentation.context.assets.open("local-kernel-golden.json").bufferedReader().use { it.readText() }
        verifyLocalGolden(text)
        val json = Json
        val root = json.parseToJsonElement(text).jsonObject
        val policy = json.decodeFromJsonElement<LocalPolicy>(root.getValue("policy"))
        val commands = root.getValue("commands").jsonArray.map { json.decodeFromJsonElement<PaperCommand>(it) }
        val db = LocalFinancialDatabase.open(instrumentation.targetContext)
        try {
            val ledger = LocalPaperLedger(db)
            val id = "00000000-0000-4000-8000-000000000101"
            val phase = args.getString("localPhase") ?: "create"
            if (phase == "create") {
                val account = ledger.create(id, "1000", root.getValue("start").jsonPrimitive.content, policy)
                assertEquals(0L, account.revision)
                commands.take(2).forEachIndexed { i, command -> ledger.submit(id, i.toLong(), command) }
                val partial = ledger.restore(id)
                val raceId = "00000000-0000-4000-8000-000000000102"
                ledger.create(raceId, "1000", root.getValue("start").jsonPrimitive.content, policy)
                val outcomes = listOf("race-a", "race-b").map { eventId -> async(Dispatchers.IO) {
                    runCatching { ledger.submit(raceId, 0, commands[0].copy(id = eventId)) }
                } }.awaitAll()
                assertEquals(1, outcomes.count { it.isSuccess })
                assertEquals(1L, ledger.restore(raceId).revision)
                try { ledger.submit(id, 2, commands[2].copy(side = "x".repeat(5000))); fail("oversized metadata accepted") } catch (_: IllegalArgumentException) { }
                assertEquals(2L, ledger.restore(id).revision)
                assertEquals(2L, partial.revision)
                assertEquals("2", partial.book.pending?.remaining)
                assertEquals("1", partial.book.quantity)
                // Exact retries do not append; conflicting payloads and optimistic revisions fail.
                assertEquals(2L, ledger.submit(id, 0, commands[0]).revision)
                try { ledger.submit(id, 2, commands[0].copy(quantity = "9")); fail("conflict accepted") } catch (_: IllegalArgumentException) { }
                try { ledger.submit(id, 0, commands[2]); fail("stale revision accepted") } catch (_: IllegalArgumentException) { }
            } else {
                require(phase == "recover")
                val before = ledger.restore(id)
                assertEquals(2L, before.revision)
                assertEquals("2", before.book.pending?.remaining)
                commands.drop(2).forEachIndexed { i, command -> ledger.submit(id, i.toLong() + 2, command) }
                val restored = ledger.restore(id)
                assertEquals(commands.size.toLong(), restored.revision)
                val expected = root.getValue("expected").jsonArray.last().jsonObject
                assertEquals(0, Decimal80.read(expected.getValue("cash").jsonPrimitive.content).compareTo(Decimal80.read(restored.book.cash)))
                assertEquals("0", restored.book.quantity)
                assertEquals("0", restored.book.basis)
                assertNull(restored.book.pending)
                // Deliberately corrupt only this disposable test journal; AEAD/integrity must fail closed.
                db.openHelper.writableDatabase.execSQL("UPDATE local_events SET payload = zeroblob(32) WHERE accountId = ? AND sequence = 1", arrayOf(id))
                try { ledger.restore(id); fail("corrupt journal accepted") } catch (_: java.security.GeneralSecurityException) { }
            }
        } finally {
            db.close()
            android.util.Log.i("LocalEngineProof", "phase=${args.getString("localPhase") ?: "create"} elapsed_ms=${android.os.SystemClock.elapsedRealtime() - started} pss_kb=${android.os.Debug.getPss()}")
        }
    }
}
