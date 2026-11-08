package pt.pocketalpha.workspace

import android.content.Context
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton
import pt.pocketalpha.local.LocalFinancialDatabase
import pt.pocketalpha.local.LocalPaperLedger

@Module @InstallIn(SingletonComponent::class)
object LocalWorkspaceModule {
    @Provides @Singleton fun financialDatabase(@ApplicationContext context: Context): LocalFinancialDatabase = LocalFinancialDatabase.open(context)
    @Provides @Singleton fun financialAuthority(database: LocalFinancialDatabase): LocalPaperLedger = LocalPaperLedger(database)
}
