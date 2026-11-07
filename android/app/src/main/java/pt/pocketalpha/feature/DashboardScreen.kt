package pt.pocketalpha.feature

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import pt.pocketalpha.core.*

@Composable fun MarketPicker(vm: WorkspaceViewModel) {
    val markets by vm.markets.collectAsStateWithLifecycle()
    val selected by vm.selected.collectAsStateWithLifecycle()
    val resources by vm.resources.collectAsStateWithLifecycle()
    var query by rememberSaveable { mutableStateOf("") }
    OutlinedTextField(query, { query = it }, label = { Text("Search registered assets / markets") },
        singleLine = true, modifier = Modifier.fillMaxWidth())
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(onClick = { vm.loadMarkets(query) }) { Text("Search") }
        OutlinedButton(onClick = { vm.loadMarkets(query, true) }) { Text("Load more") }
    }
    ResourceStatus(resources["markets"])
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items(markets, key = { it.market_id }) { market ->
            FilterChip(selected = market.market_id == selected?.market_id, onClick = { vm.select(market) },
                label = { Text("${market.symbol} · ${market.venue_id}") })
        }
    }
    if (markets.isEmpty() && resources["markets"]?.loading != true) Note("No registered markets. Providers must be configured on the server.")
}
@Composable fun TimeframePicker(vm: WorkspaceViewModel) {
    val frame by vm.timeframe.collectAsStateWithLifecycle()
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items(Timeframes.keys.toList()) { value -> FilterChip(selected = frame == value, onClick = { vm.frame(value) }, label = { Text(value) }) }
    }
}
@Composable fun DashboardScreen(vm: WorkspaceViewModel, analyze: Boolean, fullChart: Boolean = false, openChart: () -> Unit) {
    val resources by vm.resources.collectAsStateWithLifecycle()
    val selected by vm.selected.collectAsStateWithLifecycle()
    val horizon by vm.horizon.collectAsStateWithLifecycle()
    val chartResource = resources["candles"]
    val analysis = resources["analysis"]
    val report = analysis?.value.field("report")
    val panel = report.field("horizons").elements().firstOrNull { it.text("horizon") == horizon }
    LazyVerticalGrid(modifier = Modifier.testTag("dashboard-grid"), columns = GridCells.Adaptive(380.dp), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        item(span = { GridItemSpan(maxLineSpan) }) { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(if (analyze) "Analyze" else "Market overview", style = MaterialTheme.typography.headlineMedium)
            Note("Intelligence, evidence and provenance from one shared backend")
        } }
        item(span = { GridItemSpan(maxLineSpan) }) { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { MarketPicker(vm) } }
        item(span = { GridItemSpan(maxLineSpan) }) { TimeframePicker(vm) }
        item(span = { GridItemSpan(if (fullChart) maxLineSpan else 1) }) { PocketCard(selected?.symbol ?: "Select a market") {
            ResourceStatus(chartResource)
            resources["candle-head"]?.value?.let { head ->
                Note("Latest stored close ${head.field("candle").text("close_time") ?: "unavailable"} · age at fetch ${head.text("age_seconds") ?: "unknown"} seconds")
                Note("Data quality describes integrity, not freshness.")
            }
            chartResource?.value?.let { value ->
                val page = remember(value) { vm.repository.candles(value) }
                Note("Data quality: ${page.quality.text("severity") ?: "unavailable"} · ${page.quality.text("source") ?: "stored"}", page.quality.text("severity") != "OK")
                if (page.quality.text("valid") == "true") FinancialChart(page.candles) else Note("The server rejected this chart's data quality.", true)
                TextButton(onClick = { page.candles.firstOrNull()?.let { vm.loadAnalysis(java.time.Instant.parse(it.open_time)) } }, enabled = page.candles.isNotEmpty()) { Text("Load older 500-bar window") }
                Note("Bounded 500 bars · older data replaces this window")
            }
            if (chartResource?.value == null && chartResource?.loading != true) Note("Candles unavailable")
            TextButton(onClick = openChart) { Text(if (fullChart) "Return to dashboard" else "Open full chart") }
            TextButton(onClick = { vm.loadAnalysis() }) { Text("Refresh market snapshot") }
        } }
        if (!fullChart) {
            item { PocketCard("Pocket Score") { ResourceStatus(analysis); Score(report.field("pocket_score"))
                Note("Snapshot ${report.text("as_of") ?: "unavailable"} · ${report.text("report_version") ?: "no version"}")
                analysis?.value.text("unavailable_reason")?.let { Note(it, true) }
                val snapshots = resources["analysis-history"]?.value.field("items").elements().mapNotNull { it.text("as_of") }
                if (snapshots.isNotEmpty()) Choice("Historical snapshot", snapshots, report.text("as_of") ?: snapshots.first()) {
                    vm.loadAnalysis(snapshotAsOf = it)
                }
            } }
            item { PocketCard("Directional analysis & forecasts") {
                Note("Candle timeframe and forecast horizon are independent.")
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) { items(Horizons) { value ->
                    FilterChip(selected = horizon == value, onClick = { vm.horizon.value = value }, label = { Text(value) })
                } }
                Note("Historical snapshot ${report.text("as_of") ?: "unavailable"} · review each forecast's expiry")
                val decision = panel.field("directional").text("decision") ?: "UNAVAILABLE"
                Text(decision, style = MaterialTheme.typography.headlineSmall, color = when (decision) {
                    "LONG" -> Accent; "SHORT" -> Negative; "NO_TRADE" -> Amber; else -> Muted
                })
                Note(panel.text("conclusion") ?: "No stored analytical snapshot")
                Note("Forecast confidence is model metadata, not guaranteed accuracy. Scores are not probabilities.")
                Record(panel)
            } }
            item { PocketCard("Market context") {
                Note("Only stored supported provider observations are displayed. Open Fundamentals, Derivatives or News in More for source evidence.")
                Note("Execution authority remains server-side. REAL_MONEY_TRADING_AUTHORIZED = NO", true)
            } }
        }
    }
}
