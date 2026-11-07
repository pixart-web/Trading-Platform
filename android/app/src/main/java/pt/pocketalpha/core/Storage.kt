package pt.pocketalpha.core

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import androidx.room.*
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.first
import kotlinx.serialization.json.Json
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import javax.inject.Inject
import javax.inject.Singleton

private val Context.preferences by preferencesDataStore("pocket-preferences")

@Singleton class Preferences @Inject constructor(@ApplicationContext private val context: Context) {
    private val endpointKey = stringPreferencesKey("endpoint")
    suspend fun endpoint(): String = context.preferences.data.first()[endpointKey] ?: ""
    suspend fun saveEndpoint(value: String) { context.preferences.edit { it[endpointKey] = value } }
}

@Singleton class TokenVault @Inject constructor(@ApplicationContext context: Context, private val json: Json) {
    private val file = AtomicFile(File(context.noBackupFilesDir, "device-session.enc"))
    @Volatile var access: String? = null
        private set
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        return (store.getKey("pocket-session-v1", null) as? SecretKey) ?: KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder("pocket-session-v1", KeyProperties.PURPOSE_ENCRYPT or
                KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
    @Synchronized fun read(): StoredSession? {
        if (!file.baseFile.exists()) return null
        return try {
            val bytes = file.readFully()
            require(bytes.size in 29..4096)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
            json.decodeFromString<StoredSession>(cipher.doFinal(bytes.copyOfRange(12, bytes.size)).decodeToString()).also {
                require(java.time.Instant.parse(it.refresh_expires_at) > java.time.Instant.now())
            }
        } catch (_: Exception) { clear(); null }
    }
    @Synchronized fun save(tokens: Tokens) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val data = json.encodeToString(StoredSession(tokens.refresh_token, tokens.session_id, tokens.user_id, tokens.refresh_expires_at)).encodeToByteArray()
        val stream = file.startWrite()
        try { stream.write(cipher.iv + cipher.doFinal(data)); file.finishWrite(stream) }
        catch (failure: Exception) { file.failWrite(stream); throw failure }
        access = tokens.access_token
    }
    @Synchronized fun clear() { access = null; file.delete() }
}

@Entity(tableName = "snapshots", indices = [Index("fetchedAt")])
data class CachedSnapshot(@PrimaryKey val key: String, val payload: String, val fetchedAt: Long)
@Dao interface SnapshotDao {
    @Query("SELECT * FROM snapshots WHERE `key` = :key") suspend fun get(key: String): CachedSnapshot?
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun put(value: CachedSnapshot)
    @Query("DELETE FROM snapshots WHERE `key` NOT IN (SELECT `key` FROM snapshots ORDER BY fetchedAt DESC LIMIT 64)") suspend fun prune()
    @Query("DELETE FROM snapshots") suspend fun clear()
}
@Database(entities = [CachedSnapshot::class], version = 1, exportSchema = false)
abstract class PocketDatabase : RoomDatabase() { abstract fun snapshots(): SnapshotDao }
