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
    @Query("SELECT * FROM local_accounts ORDER BY id LIMIT 100") suspend fun accounts(): List<LocalAccountRow>
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
@Serializable data class AccountInfo(val id: String, val market: String, val origin: String, val policy: LocalPolicy)
@Serializable private data class PortableJournal(val version: Int = 1, val header: String, val events: List<String>, val head: String)
data class ReconciledAccount(val id: String, val revision: Long, val book: LocalBook)

/** Local financial authority independent of Activity, HTTP, provider clients and navigation. */
interface LocalFinancialAuthority {
    suspend fun restore(id: String): ReconciledAccount
    suspend fun submit(id: String, expectedRevision: Long, command: PaperCommand): ReconciledAccount
}
class LocalPaperLedger(private val db: LocalFinancialDatabase, private val cipher: LedgerCipher = LedgerCipher()) : LocalFinancialAuthority {
    var unavailableAccounts: List<String> = emptyList()
        private set
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
    suspend fun accounts(): List<AccountInfo> = db.withTransaction {
        val unavailable = mutableListOf<String>()
        val available = db.ledger().accounts().mapNotNull { row ->
            try {
                val header = json.decodeFromString<Genesis>(cipher.decrypt(row.header, row.id))
                AccountInfo(row.id, header.marketId, header.origin, header.policy)
            } catch (failure: java.security.GeneralSecurityException) { unavailable.add(row.id); null }
        }
        unavailableAccounts = unavailable
        available
    }
    suspend fun createPublic(id: String, capital: String, at: String, policy: LocalPolicy, market: String): ReconciledAccount = db.withTransaction {
        UUID.fromString(id); require(market.matches(Regex("[A-Z0-9]{2,16}-EUR")))
        require(db.ledger().accounts().size < 100) { "Experiment limit reached; existing history is preserved" }
        val initial = FinancialKernel(policy).genesis(capital, at)
        val header = json.encodeToString(Genesis(version = "local-paper-2", currency = "EUR", origin = "PUBLIC_COINBASE",
            marketId = market, strategyVersion = "MONITOR_ONLY_NO_QUALIFIED_ENTRY", capital = capital, at = at, policy = policy))
        db.ledger().create(LocalAccountRow(id, cipher.encrypt(header, id), 0, digest(header)))
        ReconciledAccount(id, 0, initial)
    }
    suspend fun history(id: String): List<Pair<PaperCommand, LocalBook>> = db.withTransaction {
        restoreLocked(id)
        db.ledger().events(id).map { row -> json.decodeFromString<RecordedEvent>(cipher.decrypt(row.payload, "$id:${row.sequence}")).let { it.command to it.after } }
    }
    suspend fun portable(id: String): String = db.withTransaction {
        restoreLocked(id)
        val row = requireNotNull(db.ledger().account(id))
        json.encodeToString(PortableJournal(header = cipher.decrypt(row.header, id), events = db.ledger().events(id).map { cipher.decrypt(it.payload, "$id:${it.sequence}") }, head = row.head))
    }
    suspend fun importPortable(value: String, allowSynthetic: Boolean = true): ReconciledAccount = db.withTransaction {
        require(value.toByteArray().size <= 8 * 1024 * 1024)
        require(db.ledger().accounts().size < 100) { "Experiment limit reached" }
        val backup = json.decodeFromString<PortableJournal>(value)
        if (!allowSynthetic) require(json.decodeFromString<Genesis>(backup.header).origin == "PUBLIC_COINBASE") { "Synthetic journals cannot enter operational mode" }
        require(backup.version == 1 && backup.events.size <= 10000)
        val id = UUID.randomUUID().toString()
        var head = digest(backup.header)
        db.ledger().create(LocalAccountRow(id, cipher.encrypt(backup.header, id), 0, head))
        backup.events.forEachIndexed { index, payload ->
            require(payload.toByteArray().size <= 4096)
            val event = json.decodeFromString<RecordedEvent>(payload)
            val hash = digest(head + "\n" + payload)
            db.ledger().append(LocalEventRow(id, index + 1L, event.command.id, cipher.encrypt(payload, "$id:${index+1}"), head, hash))
            check(db.ledger().advance(id, index.toLong(), index+1L, hash) == 1)
            head = hash
        }
        require(head == backup.head)
        restoreLocked(id)
    }
    private suspend fun restoreLocked(id: String): ReconciledAccount {
        val account = requireNotNull(db.ledger().account(id)) { "Unknown PAPER account" }
        val header = cipher.decrypt(account.header, id)
        val genesis = json.decodeFromString<Genesis>(header)
        require(genesis.mode == "PAPER" && genesis.currency == "EUR")
        require((genesis.version == "local-paper-1" && genesis.origin == "SYNTHETIC_ENGINEERING_FIXTURE" && genesis.marketId == "SYNTHETIC-EUR" && genesis.strategyVersion == "synthetic-plan-1") ||
            (genesis.version == "local-paper-2" && genesis.origin == "PUBLIC_COINBASE" && genesis.marketId.matches(Regex("[A-Z0-9]{2,16}-EUR")) && genesis.strategyVersion == "MONITOR_ONLY_NO_QUALIFIED_ENTRY"))
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
