package pt.pocketalpha.feature

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import kotlinx.serialization.json.*
import pt.pocketalpha.core.*
import java.time.Instant
import java.util.UUID
import javax.inject.Inject

@HiltViewModel class WorkspaceViewModel @Inject constructor(val repository: Repository) : ViewModel() {
    val authenticated = MutableStateFlow<Boolean?>(null)
    val origin = MutableStateFlow("")
    val message = MutableStateFlow<String?>(null)
    val busy = MutableStateFlow(false)
    val resources = MutableStateFlow<Map<String, Resource>>(emptyMap())
    val markets = MutableStateFlow<List<Market>>(emptyList())
    val selected = MutableStateFlow<Market?>(null)
    val timeframe = MutableStateFlow("1h")
    val horizon = MutableStateFlow("24H")
    private var workspaceVersion = 0
    private var marketOffset = 0
    private var search = ""
    private var chartJob: Job? = null
    private var marketJob: Job? = null
    init {
        viewModelScope.launch {
            repository.sessionInvalidated.collect { invalid ->
                if (invalid) {
                    workspaceVersion++; chartJob?.cancel(); marketJob?.cancel()
                    resources.value = emptyMap(); selected.value = null; markets.value = emptyList()
                    authenticated.value = false; message.value = "Session expired or revoked. Sign in again."
                }
            }
        }
        viewModelScope.launch {
            origin.value = repository.storedEndpoint()
            authenticated.value = repository.resume()
            if (authenticated.value == true) loadMarkets()
        }
    }
    fun login(endpoint: String, username: String, password: String) {
        if (busy.value) return
        viewModelScope.launch {
            busy.value = true; message.value = null
            try {
                repository.login(endpoint, username, password)
                workspaceVersion++; resources.value = emptyMap(); selected.value = null
                origin.value = endpoint; authenticated.value = true; loadMarkets()
            } catch (cancelled: kotlinx.coroutines.CancellationException) { throw cancelled }
            catch (_: Exception) { message.value = "Sign-in failed. Check the HTTPS server and credentials." }
            finally { busy.value = false }
        }
    }
    fun logout() {
        workspaceVersion++; chartJob?.cancel(); marketJob?.cancel()
        viewModelScope.launch {
            val revoked = repository.logout()
            resources.value = emptyMap(); markets.value = emptyList(); selected.value = null
            authenticated.value = false
            message.value = if (revoked) "Signed out; device session revoked." else
                "Local credentials cleared. Server revocation could not be confirmed; revoke this device from another session."
        }
    }
    fun loadMarkets(query: String = search, more: Boolean = false) {
        marketJob?.cancel()
        marketJob = viewModelScope.launch {
            val version = workspaceVersion
            if (!more || query != search) marketOffset = 0
            search = query
            val offset = marketOffset
            update("markets", Resource(loading = true))
            val result = repository.read("markets:$query:$offset") {
                repository.encodeMarkets(it.markets(query.take(128), offset = offset))
            }
            if (version != workspaceVersion) return@launch
            update("markets", result)
            result.value?.let { value ->
                val page = repository.markets(value)
                markets.value = if (more) (markets.value + page).distinctBy { it.market_id }.takeLast(250) else page
                if (page.isNotEmpty()) marketOffset = offset + page.size
                if (selected.value == null && page.isNotEmpty()) select(page.first())
            }
        }
    }
    fun select(market: Market) { selected.value = market; loadAnalysis() }
    fun frame(value: String) { require(value in Timeframes); timeframe.value = value; loadAnalysis() }
    fun loadAnalysis(end: Instant? = null, snapshotAsOf: String? = null) {
        val market = selected.value ?: return
        val frame = timeframe.value
        val duration = requireNotNull(Timeframes[frame])
        chartJob?.cancel()
        chartJob = viewModelScope.launch {
            update("candles", Resource(loading = true)); update("analysis", Resource(loading = true)); update("candle-head", Resource(loading = true))
            val latest = repository.read("candle-head:${market.market_id}:$frame") { api ->
                api.latestCandle(market.market_id, frame).also {
                    require(it.text("market_id") == market.market_id && it.text("candle_timeframe") == frame)
                }
            }
            update("candle-head", latest)
            val storedEnd = latest.value.field("candle").text("close_time")?.let { Instant.parse(it) }
            val fallback = Instant.now().let { Instant.ofEpochSecond(it.epochSecond / duration * duration) }
            val endStamp = (end ?: storedEnd ?: fallback).toString()
            val start = Instant.parse(endStamp).minusSeconds(duration * 500).toString()
            val chart = repository.read("candles:${market.market_id}:$frame:$endStamp") {
                val page = it.candles(market.market_id, mapOf("timeframe" to frame, "start" to start, "end" to endStamp, "limit" to "500"))
                require(page.candles.size <= 500)
                page.candles.forEach { candle -> candle.validate(market.market_id, frame) }
                require(page.candles.zipWithNext().all { (a, b) -> Instant.parse(a.open_time) < Instant.parse(b.open_time) })
                repository.encodeCandles(page)
            }
            update("candles", chart)
            val history = repository.read("analysis-history:${market.market_id}:$frame") { it.snapshots(market.market_id, frame) }
            update("analysis-history", history)
            val asOf = snapshotAsOf ?: history.value.field("items").elements().firstOrNull()?.text("as_of") ?: endStamp
            val analysis = repository.read("analysis:${market.market_id}:$frame:$asOf") {
                val value = it.analysis(market.market_id, mapOf("timeframe" to frame, "as_of" to asOf))
                validateAnalysis(value, market.market_id, frame, asOf)
                value
            }
            update("analysis", analysis)
        }
    }
    fun loadWatchlists() = read("watchlists", preserve = true) { repository.encodeWatchlists(it.watchlists()) }
    fun loadPortfolios() = read("portfolios", preserve = true) { repository.encodePortfolios(it.portfolios()) }
    fun read(key: String, cache: Boolean = true, preserve: Boolean = false, fetch: suspend (PocketApi) -> JsonElement) {
        val version = workspaceVersion
        viewModelScope.launch {
            if (version != workspaceVersion) return@launch
            update(key, if (preserve) (resources.value[key] ?: Resource()).copy(loading = true, error = null) else Resource(loading = true))
            val result = repository.read(key, cache, fetch)
            if (version == workspaceVersion) update(key, result)
        }
    }
    fun document(key: String, path: String, query: Map<String, String> = emptyMap()) = read(key) { it.document(path, query) }
    fun mutate(action: suspend (PocketApi) -> Unit, after: () -> Unit) {
        if (busy.value) return
        viewModelScope.launch {
            busy.value = true
            try {
                message.value = repository.mutate(action)
                if (message.value == null) { message.value = "Server confirmed the change."; after() }
            } finally { busy.value = false }
        }
    }
    fun createWatchlist(name: String) {
        if (name.trim().isEmpty() || name.length > 80) { message.value = "Use a name with 1–80 characters."; return }
        val id = UUID.randomUUID().toString()
        mutate({ it.createWatchlist(jsonBody("watchlist_id" to id, "name" to name.trim())); Unit }, ::loadWatchlists)
    }
    fun rename(list: Watchlist, name: String) = mutate({ it.renameWatchlist(list.watchlist_id, buildJsonObject {
        put("name", name.trim()); put("expected_revision", list.revision)
    }); Unit }, ::loadWatchlists)
    fun add(list: Watchlist) {
        val market = selected.value ?: return
        val body = buildJsonObject {
            put("member_id", UUID.randomUUID().toString()); put("expected_revision", list.revision)
            put("candle_timeframe", timeframe.value)
        }
        mutate({ it.addMember(list.watchlist_id, market.market_id, body); Unit }, ::loadWatchlists)
    }
    fun remove(list: Watchlist, member: Member) = mutate({
        it.removeMember(list.watchlist_id, member.market_id, list.revision); Unit
    }, ::loadWatchlists)
    private fun update(key: String, value: Resource) {
        val pinned = setOf("markets", "candles", "analysis", "analysis-history", "watchlists", "portfolios", "scan", "sessions")
        resources.update { previous ->
            val next = previous.minus(key) + (key to value)
            val retained = next.keys.filterNot { it in pinned }.takeLast(24).toSet()
            next.filterKeys { it in pinned || it in retained }
        }
    }
}
