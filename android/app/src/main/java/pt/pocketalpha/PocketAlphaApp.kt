package pt.pocketalpha

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import androidx.work.*
import dagger.hilt.android.HiltAndroidApp
import dagger.hilt.EntryPoint
import dagger.hilt.InstallIn
import dagger.hilt.android.EntryPointAccessors
import dagger.hilt.components.SingletonComponent
import android.content.Context
import pt.pocketalpha.core.Repository
import java.util.concurrent.TimeUnit

@HiltAndroidApp class PocketAlphaApp : Application() {
    override fun onCreate() {
        super.onCreate()
        val manager = getSystemService(NotificationManager::class.java)
        listOf("research" to "Research jobs", "risk" to "Risk alerts", "paper" to "Paper orders",
            "system" to "System health").forEach { (id, name) ->
            manager.createNotificationChannel(NotificationChannel(id, name, NotificationManager.IMPORTANCE_DEFAULT))
        }
        WorkManager.getInstance(this).cancelUniqueWork("read-cache-sync")
    }
}
@EntryPoint @InstallIn(SingletonComponent::class) interface SyncEntryPoint { fun repository(): Repository }
class CacheSyncWorker(context: Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result {
        val repository = EntryPointAccessors.fromApplication(applicationContext, SyncEntryPoint::class.java).repository()
        if (!repository.resume()) return Result.success()
        val result = repository.read("watchlists") { repository.encodeWatchlists(it.watchlists()) }
        return if (result.error != null && runAttemptCount < 3) Result.retry() else Result.success()
    }
}
