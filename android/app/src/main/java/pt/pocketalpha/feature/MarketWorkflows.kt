package pt.pocketalpha.feature

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.serialization.json.*
import pt.pocketalpha.core.*
import java.time.Instant
import java.util.UUID

@Composable fun WatchlistsScreen(vm: WorkspaceViewModel) {
    val resources by vm.resources.collectAsStateWithLifecycle()
    val selected by vm.selected.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    var name by rememberSaveable { mutableStateOf("") }
    LaunchedEffect(Unit) { vm.loadWatchlists() }
    val resource = resources["watchlists"]
    val lists = resource?.value?.let { vm.repository.watchlists(it) } ?: emptyList()
    LazyColumn(modifier = Modifier.testTag("watchlists-list"), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Text("Watchlists", style = MaterialTheme.typography.headlineMedium); ResourceStatus(resource) }
        item { PocketCard("Create list") {
            OutlinedTextField(name, { name = it.take(80) }, label = { Text("List name") }, modifier = Modifier.fillMaxWidth())
            Button(onClick = { vm.createWatchlist(name) }, enabled = !busy && resource?.offline != true && name.isNotBlank()) { Text("Create on server") }
            TextButton(onClick = vm::loadWatchlists) { Text("Refresh") }
        } }
        item { MarketPicker(vm) }
        items(lists, key = { it.watchlist_id }) { list ->
            PocketCard("${list.name} · revision ${list.revision}", modifier = Modifier.testTag("watchlist:${list.watchlist_id}")) {
                var renamed by rememberSaveable(list.watchlist_id, list.revision) { mutableStateOf(list.name) }
                OutlinedTextField(renamed, { renamed = it.take(80) }, label = { Text("Rename list") }, modifier = Modifier.fillMaxWidth())
                TextButton(onClick = { vm.rename(list, renamed) }, enabled = !busy && resource?.offline != true && renamed.isNotBlank() && renamed != list.name) { Text("Save name") }
                Button(onClick = { vm.add(list) }, enabled = !busy && resource?.offline != true && selected != null && list.members.none { it.market_id == selected?.market_id }) { Text("Add ${selected?.symbol ?: "selected market"}") }
                list.members.forEach { member ->
                    Text("${member.market_id} · ${member.candle_timeframe}")
                    TextButton(onClick = { vm.remove(list, member) }, enabled = !busy && resource?.offline != true) { Text("Remove market") }
                }
                TextButton(onClick = { vm.document("watchlist-detail:${list.watchlist_id}", "api/v1/watchlists/${list.watchlist_id}/snapshots/latest") }) { Text("Latest analytical snapshot") }
                ResourceStatus(resources["watchlist-detail:${list.watchlist_id}"])
                resources["watchlist-detail:${list.watchlist_id}"]?.value?.let { Record(it) }
                var confirmDelete by remember { mutableStateOf(false) }
                TextButton(onClick = { confirmDelete = true }, enabled = !busy && resource?.offline != true) { Text("Delete list", color = Negative) }
                if (confirmDelete) AlertDialog(onDismissRequest = { confirmDelete = false },
                    title = { Text("Delete ${list.name}?") }, text = { Text("The list is removed from active views on every client. Server snapshot and alert history is retained.") },
                    confirmButton = { TextButton(onClick = { confirmDelete = false; vm.mutate({ it.deleteWatchlist(list.watchlist_id, list.revision) }, vm::loadWatchlists) }) { Text("Delete", color = Negative) } },
                    dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("Cancel") } })
            }
        }
        if (lists.isEmpty() && resource?.loading != true) item { Note("No watchlists yet") }
    }
}

@Composable fun ScannerScreen(vm: WorkspaceViewModel) {
    val resources by vm.resources.collectAsStateWithLifecycle()
    val frame by vm.timeframe.collectAsStateWithLifecycle()
    val horizon by vm.horizon.collectAsStateWithLifecycle()
    val selected by vm.selected.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    var direction by rememberSaveable { mutableStateOf("LONG") }
    var minimum by rememberSaveable { mutableStateOf("") }
    var liquidity by rememberSaveable { mutableStateOf("") }
    var uncertainty by rememberSaveable { mutableStateOf("") }
    var all by rememberSaveable { mutableStateOf(true) }
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Text("Opportunity Scanner", style = MaterialTheme.typography.headlineMedium); Note("Server ranking · policy groups stay independent · scores are not probabilities") }
        item { TimeframePicker(vm); Choice("Horizon", Horizons, horizon) { vm.horizon.value = it } }
        item { PocketCard("Universe & risk filters") {
            Row { Checkbox(all, { all = it }); Text("All registered markets") }
            if (!all) MarketPicker(vm)
            Choice("Direction", listOf("LONG", "SHORT", "BOTH"), direction) { direction = it }
            OutlinedTextField(minimum, { minimum = it }, label = { Text("Minimum score (0–100), optional") }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(liquidity, { liquidity = it }, label = { Text("Minimum liquidity (0–1), optional") }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(uncertainty, { uncertainty = it }, label = { Text("Maximum uncertainty (0–1), optional") }, modifier = Modifier.fillMaxWidth())
            Button(onClick = {
                try {
                    listOf(minimum to "100", liquidity to "1", uncertainty to "1").forEach { (value, upper) ->
                        if (value.isNotBlank()) require(value.toBigDecimal() >= java.math.BigDecimal.ZERO && value.toBigDecimal() <= upper.toBigDecimal())
                    }
                    val asOf = Instant.now().toString()
                    val body = buildJsonObject {
                        put("scan_id", UUID.randomUUID().toString()); put("candle_timeframe", frame)
                        put("horizon", horizon); put("as_of", asOf)
                        putJsonObject("filters") {
                            putJsonArray("directions") { if (direction != "SHORT") add("LONG"); if (direction != "LONG") add("SHORT") }
                            if (!all) putJsonArray("market_ids") { selected?.let { add(it.market_id) } }
                            if (minimum.isNotBlank()) put("minimum_score", minimum)
                            if (liquidity.isNotBlank()) put("minimum_liquidity", liquidity)
                            if (uncertainty.isNotBlank()) put("maximum_uncertainty", uncertainty)
                            put("max_results_per_policy", 50)
                        }
                    }
                    vm.read("scan", cache = false) { api -> api.scan(body).also { validateScan(it, frame, horizon, asOf) } }
                } catch (_: Exception) { vm.message.value = "Enter finite decimal filter values within the indicated ranges." }
            }, enabled = !busy && resources["scan"]?.loading != true && (all || selected != null)) { Text("Run server scan") }
            TextButton(onClick = { vm.document("scan-history", "api/v1/scans", mapOf("limit" to "20")) }) { Text("Recent scans") }
        } }
        item { PocketCard("Rankings & exclusion evidence") { ResourceStatus(resources["scan"]); Record(resources["scan"]?.value) } }
        resources["scan-history"]?.let { history -> item { PocketCard("Recent scans") { ResourceStatus(history); Record(history.value) } } }
    }
}

@Composable fun Choice(label: String, values: List<String>, selected: String, onSelect: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        OutlinedButton(onClick = { expanded = true }) { Text("$label: $selected") }
        DropdownMenu(expanded, onDismissRequest = { expanded = false }) {
            values.forEach { value -> DropdownMenuItem(text = { Text(value) }, onClick = { onSelect(value); expanded = false }) }
        }
    }
}
