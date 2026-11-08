package pt.pocketalpha.workspace

import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec

/** Independent password-derived export key. The device Keystore key is never exported. */
object PortableBackup {
    private val magic = byteArrayOf(80, 65, 66, 1)
    private fun key(password: String, salt: ByteArray): SecretKeySpec {
        require(password.length in 12..256) { "Use a backup password of 12–256 characters" }
        val spec = PBEKeySpec(password.toCharArray(), salt, 600000, 256)
        return try { SecretKeySpec(SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).encoded, "AES") }
        finally { spec.clearPassword() }
    }
    fun encrypt(value: String, password: String): ByteArray {
        val bytes = value.toByteArray(Charsets.UTF_8); require(bytes.size <= 8 * 1024 * 1024)
        val salt = ByteArray(16).also { SecureRandom().nextBytes(it) }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key(password, salt)); updateAAD(magic + salt) }
        return magic + salt + cipher.iv + cipher.doFinal(bytes)
    }
    fun decrypt(value: ByteArray, password: String): String {
        require(value.size in 48..(8 * 1024 * 1024 + 48) && value.copyOfRange(0, 4).contentEquals(magic))
        val salt = value.copyOfRange(4, 20)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.DECRYPT_MODE, key(password, salt), GCMParameterSpec(128, value.copyOfRange(20, 32)))
            updateAAD(magic + salt)
        }
        return cipher.doFinal(value.copyOfRange(32, value.size)).toString(Charsets.UTF_8)
    }
}
