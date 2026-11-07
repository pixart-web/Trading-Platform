package pt.pocketalpha.local

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import androidx.room.*
import androidx.room.withTransaction
import java.security.KeyStore
import java.security.MessageDigest
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Entity(tableName = "local_accounts")
data class LocalAccountRow(@PrimaryKey val id: String, val header: ByteArray,
    val revision: Long, val head: String)
@Entity(tableName = "local_events", primaryKeys = ["accountId", "sequence"],
    indices = [Index(value = ["accountId", "eventId"], unique = true)],
    foreignKeys = [ForeignKey(entity = LocalAccountRow::class, parentColumns = ["id"], childColumns = ["accountId"])])
data class LocalEventRow(val accountId: String, val sequence: Long, val eventId: String,
    val payload: ByteArray, val previous: String, val hash: String)
@Dao interface LocalLedgerDao {
    @Query("SELECT * FROM local_accounts WHERE id = :id") suspend fun account(id: String): LocalAccountRow?
    @Insert suspend fun create(row: LocalAccountRow)
    @Query("SELECT * FROM local_events WHERE accountId = :id ORDER BY sequence LIMIT 10001") suspend fun events(id: String): List<LocalEventRow>
    @Insert suspend fun append(row: LocalEventRow)
    @Query("UPDATE local_accounts SET revision = :revision, head = :head WHERE id = :id AND revision = :expected")
    suspend fun advance(id: String, expected: Long, revision: Long, head: String): Int
}
@Database(entities = [LocalAccountRow::class, LocalEventRow::class], version = 1, exportSchema = false)
abstract class LocalFinancialDatabase : RoomDatabase() {
    abstract fun ledger(): LocalLedgerDao
    companion object {
        fun open(context: Context): LocalFinancialDatabase = Room.databaseBuilder(context,
            LocalFinancialDatabase::class.java, "local-financial-authority-v1.db").build()
    }
}
/** Device-bound encrypted payloads; intentionally not a portable backup format. */
class LedgerCipher {
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        return (store.getKey("pocket-local-financial-v1", null) as? SecretKey)
            ?: KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
                init(KeyGenParameterSpec.Builder("pocket-local-financial-v1", KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
            }.generateKey()
    }
    fun encrypt(value: String, identity: String): ByteArray {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()); updateAAD(identity.toByteArray(Charsets.UTF_8)) }
        return cipher.iv + cipher.doFinal(value.toByteArray(Charsets.UTF_8))
    }
    fun decrypt(value: ByteArray, identity: String): String {
        require(value.size in 29..65536)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, value.copyOfRange(0, 12)))
            updateAAD(identity.toByteArray(Charsets.UTF_8))
        }
        return cipher.doFinal(value.copyOfRange(12, value.size)).toString(Charsets.UTF_8)
    }
}
@Serializable private data class Genesis(val version: String = "local-paper-1", val mode: String = "PAPER",
    val currency: String, val origin: String, val marketId: String = "SYNTHETIC-EUR",
    val strategyVersion: String = "synthetic-plan-1", val capital: String, val at: String, val policy: LocalPolicy)
@Serializable private data class RecordedEvent(val command: PaperCommand, val after: LocalBook)
data class ReconciledAccount(val id: String, val revision: Long, val book: LocalBook)

/** Local financial authority independent of Activity, HTTP, provider clients and navigation. */
interface LocalFinancialAuthority {
    suspend fun restore(id: String): ReconciledAccount
    suspend fun submit(id: String, expectedRevision: Long, command: PaperCommand): ReconciledAccount
}
class LocalPaperLedger(private val db: LocalFinancialDatabase, private val cipher: LedgerCipher = LedgerCipher()) : LocalFinancialAuthority {
    private val json = Json { encodeDefaults = true; ignoreUnknownKeys = false }
    private fun digest(text: String) = MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    suspend fun create(id: String, capital: String, at: String, policy: LocalPolicy): ReconciledAccount = db.withTransaction {
        UUID.fromString(id)
        val header = json.encodeToString(Genesis(currency = "EUR", origin = "SYNTHETIC_ENGINEERING_FIXTURE", capital = capital, at = at, policy = policy))
        val initial = FinancialKernel(policy).genesis(capital, at)
        val old = db.ledger().account(id)
        if (old != null) {
            require(cipher.decrypt(old.header, id) == header) { "Conflicting account identity" }
            return@withTransaction restoreLocked(id)
        }
        db.ledger().create(LocalAccountRow(id, cipher.encrypt(header, id), 0, digest(header)))
        ReconciledAccount(id, 0, initial)
    }
    private suspend fun restoreLocked(id: String): ReconciledAccount {
        val account = requireNotNull(db.ledger().account(id)) { "Unknown PAPER account" }
        val header = cipher.decrypt(account.header, id)
        val genesis = json.decodeFromString<Genesis>(header)
        require(genesis.version == "local-paper-1" && genesis.mode == "PAPER" && genesis.currency == "EUR" && genesis.origin == "SYNTHETIC_ENGINEERING_FIXTURE" && genesis.marketId == "SYNTHETIC-EUR" && genesis.strategyVersion == "synthetic-plan-1")
        val engine = FinancialKernel(genesis.policy)
        var book = engine.genesis(genesis.capital, genesis.at)
        var head = digest(header)
        val events = db.ledger().events(id)
        check(events.size.toLong() == account.revision && events.size <= 10000) { "Journal revision mismatch" }
        val ids = mutableSetOf<String>()
        events.forEachIndexed { index, event ->
            check(event.sequence == index.toLong() + 1 && event.previous == head && ids.add(event.eventId))
            val payload = cipher.decrypt(event.payload, "$id:${event.sequence}")
            check(event.hash == digest(head + "\n" + payload)) { "Journal hash mismatch" }
            val recorded = json.decodeFromString<RecordedEvent>(payload)
            check(recorded.command.id == event.eventId)
            book = engine.apply(book, recorded.command)
            check(book == recorded.after) { "Financial reconstruction mismatch" }
            head = event.hash
        }
        engine.validateState(book)
        check(head == account.head)
        return ReconciledAccount(id, account.revision, book)
    }
    override suspend fun restore(id: String): ReconciledAccount = db.withTransaction { restoreLocked(id) }
    override suspend fun submit(id: String, expectedRevision: Long, command: PaperCommand): ReconciledAccount = db.withTransaction {
        val current = restoreLocked(id)
        val rows = db.ledger().events(id)
        val duplicate = rows.find { it.eventId == command.id }
        if (duplicate != null) {
            val old = json.decodeFromString<RecordedEvent>(cipher.decrypt(duplicate.payload, "$id:${duplicate.sequence}"))
            require(old.command == command) { "Conflicting idempotency key" }
            return@withTransaction current
        }
        require(current.revision == expectedRevision && current.revision < 10000) { "Revision conflict or journal budget exceeded" }
        val account = requireNotNull(db.ledger().account(id))
        val genesis = json.decodeFromString<Genesis>(cipher.decrypt(account.header, id))
        val engine = FinancialKernel(genesis.policy)
        val next = engine.apply(current.book, command).also { engine.validateState(it) }
        val payload = json.encodeToString(RecordedEvent(command, next))
        require(payload.toByteArray(Charsets.UTF_8).size <= 4096) { "Financial event byte budget exceeded" }
        val hash = digest(account.head + "\n" + payload)
        val sequence = current.revision + 1
        db.ledger().append(LocalEventRow(id, sequence, command.id, cipher.encrypt(payload, "$id:$sequence"), account.head, hash))
        check(db.ledger().advance(id, current.revision, sequence, hash) == 1)
        ReconciledAccount(id, sequence, next)
    }
}
