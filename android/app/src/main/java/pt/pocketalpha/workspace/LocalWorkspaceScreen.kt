package pt.pocketalpha.workspace

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.BackHandler
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.time.Instant
import pt.pocketalpha.local.*
import pt.pocketalpha.feature.*

@Composable fun LocalWorkspaceScreen(onServerClient: () -> Unit, vm: LocalWorkspaceModel = hiltViewModel()) {
    val markets by vm.markets.collectAsStateWithLifecycle()
    val selected by vm.selected.collectAsStateWithLifecycle()
    val candles by vm.candles.collectAsStateWithLifecycle()
    val lockedAccounts by vm.lockedAccounts.collectAsStateWithLifecycle()
    val accounts by vm.accounts.collectAsStateWithLifecycle()
    val account by vm.account.collectAsStateWithLifecycle()
    val history by vm.history.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    val networkBusy by vm.networkBusy.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val connected by vm.connected.collectAsStateWithLifecycle()
    var page by rememberSaveable { mutableStateOf("Overview") }
    BackHandler(enabled = page != "Overview") { page = "Overview" }
    var capital by rememberSaveable { mutableStateOf("1000") }
    var quantity by rememberSaveable { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var backupMessage by remember { mutableStateOf<String?>(null) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_STOP) vm.interrupted() }
        lifecycle.addObserver(observer); onDispose { lifecycle.removeObserver(observer) }
    }
    val export = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/octet-stream")) { uri ->
        if (uri != null) scope.launch {
            try { val bytes = vm.export(password); withContext(Dispatchers.IO) { requireNotNull(context.contentResolver.openOutputStream(uri)).use { it.write(bytes) } }; backupMessage = "Encrypted backup written" }
            catch (failure: Exception) { backupMessage = failure.message }; password = ""
        }
    }
    val restore = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) scope.launch {
            try {
                val bytes = withContext(Dispatchers.IO) { requireNotNull(context.contentResolver.openInputStream(uri)).use { input ->
                    val out = java.io.ByteArrayOutputStream(); val buffer = ByteArray(8192)
                    while (true) { val n = input.read(buffer); if (n < 0) break; require(out.size() + n <= 8 * 1024 * 1024 + 48); out.write(buffer,0,n) }; out.toByteArray()
                } }
                vm.restore(bytes, password)
            } catch (failure: Exception) { backupMessage = failure.message }; password = ""
        }
    }
    val wide = with(LocalDensity.current) { LocalWindowInfo.current.containerSize.width.toDp() >= 840.dp }
    Surface(Modifier.fillMaxSize(), color = Base, contentColor = MaterialTheme.colorScheme.onBackground) {
    Row(Modifier.fillMaxSize()) {
        if (wide) Surface(Modifier.width(212.dp).fillMaxHeight(), color = Panel) { Column(Modifier.padding(16.dp)) {
            Text("POCKET ALPHA", color = Accent, style = MaterialTheme.typography.titleMedium)
            Text("LOCAL · PAPER ONLY", color = Muted, modifier = Modifier.padding(vertical = 20.dp))
            listOf("Overview", "Analyze", "Paper Trading", "History", "Backup & Settings").forEach { item ->
                NavigationDrawerItem(label = { Text(item) }, selected = page == item, onClick = { page = item })
            }
        } }
        LazyVerticalGrid(columns = GridCells.Adaptive(440.dp), modifier = Modifier.weight(1f).fillMaxHeight().testTag("local-workspace-grid"), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            item(span = { GridItemSpan(maxLineSpan) }) { Column { Text("Local workspace", style = MaterialTheme.typography.headlineMedium); Text(androidx.compose.ui.res.stringResource(pt.pocketalpha.R.string.app_name), color = Accent); Note("Private tablet storage · no Pocket Alpha server · real-money execution disabled") } }
            if (!wide) item { Row { listOf("Overview", "Paper Trading", "Backup & Settings").forEach { title -> TextButton(onClick = { page = title }) { Text(title) } } } }
            if (busy || networkBusy) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
            if (lockedAccounts > 0) item { Note("$lockedAccounts experiments cannot be decrypted. They were preserved; restore a portable backup as a new experiment.", true) }
            error?.let { item { Note(it, true) } }
            item(span = { GridItemSpan(maxLineSpan) }) { PocketCard("Public market · $selected") {
                Text(if (connected) "Provider response verified" else "Disconnected / cached observations only", color = if(connected) Accent else Amber)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    markets.filter { it.id in setOf("BTC-EUR", "ETH-EUR", selected) }.forEach { market -> OutlinedButton(onClick = { vm.select(market.id) }, enabled = !busy && !networkBusy) { Text(market.id) } }
                    TextButton(onClick = { vm.refresh() }, enabled = !busy && !networkBusy) { Text("Refresh public data") }
                }
                Text("${markets.size} discovered EUR spot products · H1 closed candles · Coinbase Exchange", color = Muted)
                candles.lastOrNull()?.let { last ->
                    Text("${last.close} EUR", style = MaterialTheme.typography.headlineSmall)
                    Note("Last close ${last.close_time} · received ${last.received_at}")
                    Note("Age ${java.time.Duration.between(Instant.parse(last.close_time), Instant.now()).seconds.coerceAtLeast(0)} seconds; historical bar proxy, not a live bid/ask")
                }
            } }
            if (page == "Overview" || page == "Analyze") {
                if (candles.isNotEmpty()) item { PocketCard("Price & volume · actual stored observations") { FinancialChart(candles, Modifier.height(380.dp)) } }
                item { PocketCard("Validated local analysis") {
                    val historyValues = candles.takeLast(200).map { CausalClose(it.close,it.close_time,it.received_at) }
                    listOf("SMA", "EMA").forEach { kind ->
                        val result = remember(candles,kind) { runCatching { LocalIndicators.calculate(historyValues,20,kind,Instant.now().toString()).lastOrNull() }.getOrNull() }
                        Text("$kind 20 · ${result?.value?.let { pt.pocketalpha.core.axisPriceLabel(it) } ?: result?.reason ?: "Unavailable"}")
                    }
                    Note("Technical policy: decimal50 HALF_EVEN. Pocket Score, forecasts and directional models are unavailable until their native qualification passes.")
                } }
            }
            if (page == "Paper Trading" || page == "Overview") {
                item { PocketCard("PAPER experiments · virtual EUR") {
                    OutlinedTextField(capital, { capital = it }, label = { Text("Initial virtual capital EUR") }, singleLine = true)
                    Button(onClick = { vm.create(capital) }, enabled = !busy && markets.any { it.id == selected }) { Text("Create new PAPER experiment") }
                    Note("UTC day rollover is not enabled: processing stops at the day boundary. Preserve the old account and create a new experiment.", true)
                    Note("New experiments preserve all previous journals. One market and one pending order per account; consolidated multi-market accounting is not enabled.")
                    accounts.forEach { info -> TextButton(onClick = { vm.open(info.id) }, enabled = !busy) { Text("${info.market} · ${info.id.take(8)}") } }
                } }
                account?.let { current -> item { PocketCard("Authoritative local account · revision ${current.revision}") {
                    Text("Cash ${current.book.cash} EUR · position ${current.book.quantity} · cost basis ${current.book.basis} EUR")
                    Text("Realized P&L ${current.book.realized} EUR · fees ${current.book.fees} EUR")
                    val last = candles.lastOrNull()
                    if (last != null && accounts.any { it.id == current.id && it.market == selected }) {
                        val info = accounts.first { it.id == current.id }
                        val valuation = FinancialKernel(info.policy).valuation(current.book,last.close)
                        Text("Available cash ${valuation.availableCash} EUR · reserved ${valuation.reservedCash} EUR")
                        Text("Marked equity ${valuation.equity} EUR · unrealized P&L ${valuation.unrealized} EUR · mark as of ${last.close_time}")
                    }
                    Text("Pending ${current.book.pending?.let { "${it.side} ${it.remaining}" } ?: "none"} · ${current.book.reason ?: "No decisions"}")
                    Note("Simulation assumptions: fee10bps, spread10bps, slippage5bps, impact5bps; max order100 EUR, exposure10%, daily loss3%, drawdown10%. These are model assumptions, not measured exchange fees.")
                    OutlinedTextField(quantity, { quantity = it }, label = { Text("Manual PAPER quantity") }, singleLine = true)
                    Row { listOf("BUY", "SELL").forEach { side -> TextButton(onClick = { vm.order(side,quantity) }, enabled = connected && !busy && !current.book.halted) { Text("PAPER $side") } } }
                    OutlinedButton(onClick = { vm.processLatest() }, enabled = connected && !busy && !current.book.halted) { Text("Process newly observed closed bar") }
                    Button(onClick = { vm.stop() }, enabled = !busy && !current.book.halted) { Text("Emergency stop experiment") }
                    Note("Autopilot unavailable: no qualified native entry strategy/forecast. Automatic orders are blocked. Manual simulation only; no background execution or delayed/recovered order submission.", true)
                } } }
            }
            if (page == "History" || page == "Paper Trading") items(history.asReversed().take(100)) { (command, state) ->
                PocketCard("${command.kind} · ${command.at}") { Text("${command.side} ${command.quantity} · ${state.reason ?: "RISK_APPROVED"}"); Text("Cash ${state.cash} EUR · quantity ${state.quantity} · fees ${state.fees}") }
            }
            if (page == "Backup & Settings") item { PocketCard("Portable encrypted backup") {
                OutlinedTextField(password, { password = it }, label = { Text("Backup password (12+ characters)") }, visualTransformation = PasswordVisualTransformation(), keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Password, autoCorrectEnabled = false))
                Button(onClick = { export.launch("pocket-alpha-paper.pab") }, enabled = account != null && password.length >= 12 && !busy) { Text("Export encrypted experiment") }
                OutlinedButton(onClick = { restore.launch(arrayOf("application/octet-stream", "*/*")) }, enabled = password.length >= 12 && !busy) { Text("Restore as new experiment") }
                backupMessage?.let { Note(it) }
                Note("PBKDF2-SHA256 600,000 iterations + AES-GCM. Wrong passwords or modified journals are rejected atomically. Device keys are never exported. Biometric gating is not implemented.")
                OutlinedButton(onClick = onServerClient) { Text("Open optional legacy server client") }
            } }
        }
    }
    }
}
