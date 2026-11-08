package pt.pocketalpha.workspace

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import javax.inject.Inject
import java.time.Instant
import java.util.UUID
import pt.pocketalpha.local.*
import pt.pocketalpha.core.Candle

@HiltViewModel class LocalWorkspaceModel @Inject constructor(private val ledger: LocalPaperLedger,
    private val provider: PublicMarkets) : ViewModel() {
    val markets = MutableStateFlow<List<PublicMarket>>(emptyList())
    val selected = MutableStateFlow("BTC-EUR")
    val candles = MutableStateFlow<List<Candle>>(emptyList())
    val lockedAccounts = MutableStateFlow(0)
    val accounts = MutableStateFlow<List<AccountInfo>>(emptyList())
    val account = MutableStateFlow<ReconciledAccount?>(null)
    val history = MutableStateFlow<List<Pair<PaperCommand,LocalBook>>>(emptyList())
    val error = MutableStateFlow<String?>(null)
    val networkBusy = MutableStateFlow(false)
    val connected = MutableStateFlow(false)
    private val sessionOrders = mutableSetOf<String>()
    val busy = MutableStateFlow(false)
    private var lastRefresh = 0L
    init { run {
        reloadAccounts()
        accounts.value.firstOrNull()?.let { info -> account.value = ledger.restore(info.id); selected.value = info.market; history.value = ledger.history(info.id) }
        candles.value = provider.cached(selected.value)
        refresh()
    } }
    private fun run(block: suspend () -> Unit) { viewModelScope.launch {
        if (busy.value) return@launch
        busy.value = true; error.value = null
        try { block() } catch (cancelled: kotlinx.coroutines.CancellationException) { throw cancelled }
        catch (failure: Exception) { connected.value = false; sessionOrders.clear(); error.value = failure.message ?: "Operation unavailable" }
        finally { busy.value = false }
    } }
    private suspend fun reloadAccounts() {
        accounts.value = ledger.accounts().filter { it.origin == "PUBLIC_COINBASE" }
        lockedAccounts.value = ledger.unavailableAccounts.size
    }
    private suspend fun refreshData() {
        if (markets.value.isEmpty()) markets.value = provider.discover()
        val now = System.currentTimeMillis()
        require(now - lastRefresh >= 60000 || candles.value.isEmpty()) { "Historical refresh limited to once per minute" }
        if (now - lastRefresh > 120000) sessionOrders.clear()
        lastRefresh = now
        val requested = selected.value
        val response = provider.refresh(requested)
        if (selected.value == requested) { candles.value = response; connected.value = true }
    }
    private fun network(block: suspend () -> Unit) { viewModelScope.launch {
        if (networkBusy.value) return@launch
        networkBusy.value = true; connected.value = false
        try { block() } catch (cancelled: kotlinx.coroutines.CancellationException) { throw cancelled }
        catch (failure: Exception) { error.value = failure.message; sessionOrders.clear() }
        finally { networkBusy.value = false }
    } }
    fun refresh() = network { refreshData() }
    fun select(market: String) = network {
        require(markets.value.any { it.id == market })
        selected.value = market; connected.value = false; lastRefresh = 0; sessionOrders.clear(); account.value = null; history.value = emptyList()
        candles.value = provider.cached(market)
        refreshData()
    }
    fun open(id: String) = run {
        val info = accounts.value.first { it.id == id }
        account.value = ledger.restore(id); history.value = ledger.history(id)
        if (selected.value != info.market) { connected.value = false; sessionOrders.clear(); selected.value = info.market; candles.value = provider.cached(info.market); lastRefresh = 0 }
    }
    fun create(capital: String) = run {
        val market = markets.value.first { it.id == selected.value }
        val policy = LocalPolicy("local-public-conservative-1", "10", "10", "5", "5", "0.05", "0.01", market.step,
            market.step, market.minimum, "100", "0.10", "0.10", "0.03", 7200, "20", 3600, false)
        account.value = ledger.createPublic(UUID.randomUUID().toString(), capital, Instant.now().toString(), policy, market.id)
        history.value = emptyList(); reloadAccounts()
    }
    fun order(side: String, quantity: String) = run {
        require(connected.value) { "Provider connection not verified" }
        val active = requireNotNull(account.value)
        val last = candles.value.lastOrNull() ?: error("No provider data")
        require(!last.synthetic && last.market_id == accounts.value.first { it.id == active.id }.market)
        require(Instant.now().minusSeconds(7200) <= Instant.parse(last.close_time)) { "Stale provider data" }
        account.value = ledger.submit(active.id, active.revision, PaperCommand(UUID.randomUUID().toString(), Instant.now().toString(), "ORDER",
            side, quantity, last.close, last.close_time))
        account.value?.book?.pending?.id?.let { sessionOrders.add(it) }
        history.value = ledger.history(active.id)
    }
    fun processLatest() = run {
        require(connected.value) { "Provider connection not verified" }
        val active = requireNotNull(account.value)
        val last = candles.value.lastOrNull() ?: error("No provider data")
        require(last.market_id == accounts.value.first { it.id == active.id }.market && !last.synthetic)
        require(Instant.now().minusSeconds(7200) <= Instant.parse(last.close_time)) { "Stale provider data" }
        require(active.book.pending == null || active.book.pending.id in sessionOrders) { "Recovered/interrupted order is blocked; stop and create a new experiment" }
        require(Instant.now().minusSeconds(90) <= Instant.parse(last.close_time)) { "Bar was not observed near its close; delayed fills are blocked" }
        require(active.book.lastBarOpen == null || Instant.parse(last.open_time) > Instant.parse(active.book.lastBarOpen)) { "No new causally eligible bar; no historical fill submitted" }
        account.value = ledger.submit(active.id, active.revision, PaperCommand("coinbase:${last.open_time}", Instant.now().toString(), "BAR",
            price = last.close, quoteClose = last.close_time, barOpen = last.open_time, volume = last.volume))
        history.value = ledger.history(active.id)
    }
    fun stop() = run {
        val active = requireNotNull(account.value)
        account.value = ledger.submit(active.id, active.revision, PaperCommand(UUID.randomUUID().toString(), Instant.now().toString(), "KILL"))
        history.value = ledger.history(active.id)
    }
    suspend fun export(password: String): ByteArray = withContext(Dispatchers.IO) {
        PortableBackup.encrypt(ledger.portable(requireNotNull(account.value).id), password)
    }
    fun restore(bytes: ByteArray, password: String) = run {
        account.value = withContext(Dispatchers.IO) { ledger.importPortable(PortableBackup.decrypt(bytes, password), allowSynthetic = false) }
        connected.value = false; sessionOrders.clear(); lastRefresh = 0
        reloadAccounts(); history.value = ledger.history(requireNotNull(account.value).id)
        selected.value = accounts.value.first { it.id == requireNotNull(account.value).id }.market
        candles.value = provider.cached(selected.value)
    }
    fun interrupted() { sessionOrders.clear(); connected.value = false }
}
