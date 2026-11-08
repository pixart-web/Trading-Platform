package pt.pocketalpha

import org.junit.Assert.*
import org.junit.Test
import pt.pocketalpha.workspace.*
import java.time.Instant

class OperationalWorkspaceTest {
    @Test fun normalizesActualProviderSchemaWithoutFloatingPointLoss() {
        val rows = CoinbaseParser.candles("[[3600,99,103,100,102.123456789,4.5],[0,98,102,99,100,3]]", "BTC-EUR", Instant.ofEpochSecond(7200))
        assertEquals("102.123456789", rows.last().close)
        assertEquals("1970-01-01T00:00:00Z", rows.first().open_time)
        assertFalse(rows.last().synthetic)
        assertEquals("coinbase-exchange-public", rows.last().source)
    }
    @Test fun excludesIncompleteBarsAndRejectsInvalidOhlcAndDuplicateBuckets() {
        assertTrue(CoinbaseParser.candles("[[3600,99,103,100,102,4]]", "BTC-EUR", Instant.ofEpochSecond(7199)).isEmpty())
        assertThrows(IllegalArgumentException::class.java) { CoinbaseParser.candles("[[0,101,100,99,100,4]]", "BTC-EUR", Instant.ofEpochSecond(7200)) }
        assertThrows(IllegalArgumentException::class.java) { CoinbaseParser.candles("[[0,98,102,99,100,4],[0,98,102,99,100,4]]", "BTC-EUR", Instant.ofEpochSecond(7200)) }
    }
    @Test fun portableEncryptionRejectsWrongPasswordsAndModifiedExports() {
        val text = "Synthetic unit-test journal, not a provider observation"
        val password = "unit-test-export-password" // pragma: allowlist secret; test fixture
        val bytes = PortableBackup.encrypt(text,password)
        assertEquals(text, PortableBackup.decrypt(bytes,password))
        assertThrows(java.security.GeneralSecurityException::class.java) { PortableBackup.decrypt(bytes,"incorrect-test-password") }
        val changed = bytes.clone(); changed[changed.lastIndex] = (changed.last().toInt() xor 1).toByte()
        assertThrows(java.security.GeneralSecurityException::class.java) { PortableBackup.decrypt(changed,password) }
    }
}
