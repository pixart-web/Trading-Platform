package pt.pocketalpha.feature

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.serialization.json.*
import pt.pocketalpha.core.*
import java.time.Instant
import java.util.UUID

@Composable fun PortfolioScreen(vm: WorkspaceViewModel) {
    val resources by vm.resources.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    var name by rememberSaveable { mutableStateOf("") }
    var currency by rememberSaveable { mutableStateOf("USD") }
    var createId by rememberSaveable(name, currency) { mutableStateOf(UUID.randomUUID().toString()) }
    LaunchedEffect(Unit) { vm.loadPortfolios() }
    val resource = resources["portfolios"]
    val portfolios = resource?.value?.let { vm.repository.portfolios(it) } ?: emptyList()
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Text("Manual portfolios", style = MaterialTheme.typography.headlineMedium)
            Note("MANUAL accounting records. These are not broker deposits, orders or verified fills. PAPER balances are separate.", true)
            ResourceStatus(resource) }
        item { PocketCard("Create manual portfolio") {
            OutlinedTextField(name, { name = it.take(80) }, label = { Text("Portfolio name") }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(currency, { currency = it.uppercase().take(12) }, label = { Text("Base currency") }, modifier = Modifier.fillMaxWidth())
            Button(onClick = {
                val body = jsonBody("portfolio_id" to createId, "name" to name.trim(), "base_currency" to currency)
                vm.mutate({ it.createPortfolio(body); Unit }) { vm.loadPortfolios(); name = ""; createId = UUID.randomUUID().toString() }
            }, enabled = !busy && resource?.offline != true && name.isNotBlank() && currency.matches(Regex("[A-Z0-9]{2,12}"))) { Text("Create on server") }
            TextButton(onClick = vm::loadPortfolios) { Text("Refresh") }
        } }
        items(portfolios, key = { it.portfolio_id }) { portfolio ->
            PortfolioCard(vm, portfolio, resource?.offline == true)
        }
        if (portfolios.isEmpty() && resource?.loading != true) item { Note("No manual portfolios") }
    }
}
@Composable private fun PortfolioCard(vm: WorkspaceViewModel, portfolio: Portfolio, offline: Boolean) {
    val resources by vm.resources.collectAsStateWithLifecycle()
    val market by vm.selected.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    var kind by rememberSaveable(portfolio.portfolio_id) { mutableStateOf("DEPOSIT") }
    var amount by rememberSaveable(portfolio.portfolio_id) { mutableStateOf("") }
    var quantity by rememberSaveable(portfolio.portfolio_id) { mutableStateOf("") }
    var price by rememberSaveable(portfolio.portfolio_id) { mutableStateOf("") }
    var fee by rememberSaveable(portfolio.portfolio_id) { mutableStateOf("0") }
    var password by remember { mutableStateOf("") }
    var entryId by rememberSaveable(portfolio.portfolio_id, kind, amount, quantity, price, fee, market?.market_id) { mutableStateOf(UUID.randomUUID().toString()) }
    var occurredAt by rememberSaveable(entryId) { mutableStateOf(Instant.now().toString()) }
    var expanded by rememberSaveable(portfolio.portfolio_id) { mutableStateOf(false) }
    val key = "portfolio:${portfolio.portfolio_id}"
    fun refresh() {
        vm.document(key, "api/v1/portfolios/${portfolio.portfolio_id}/snapshot", mapOf("as_of" to Instant.now().toString()))
        vm.document("$key:entries", "api/v1/portfolios/${portfolio.portfolio_id}/entries", mapOf("limit" to "50"))
        vm.document("$key:intelligence", "api/v1/portfolios/${portfolio.portfolio_id}/intelligence", mapOf("limit" to "10"))
    }
    LaunchedEffect(portfolio.portfolio_id, portfolio.revision) { refresh() }
    PocketCard("${portfolio.name} · ${portfolio.base_currency} · r${portfolio.revision}") {
        ResourceStatus(resources[key]); Record(resources[key]?.value)
        TextButton(onClick = { refresh() }) { Text("Refresh server valuation") }
        TextButton(onClick = { expanded = !expanded }) { Text(if (expanded) "Hide accounting form" else "Record manual accounting entry") }
        if (expanded) {
            Choice("Entry type", listOf("DEPOSIT", "WITHDRAWAL", "BUY", "SELL"), kind) { kind = it }
            if (kind in listOf("DEPOSIT", "WITHDRAWAL")) OutlinedTextField(amount, { amount = it }, label = { Text("Cash amount") }, modifier = Modifier.fillMaxWidth())
            else {
                MarketPicker(vm)
                OutlinedTextField(quantity, { quantity = it }, label = { Text("Quantity") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(price, { price = it }, label = { Text("Unit price") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(fee, { fee = it }, label = { Text("Fee") }, modifier = Modifier.fillMaxWidth())
            }
            Note("Record only an accounting event that actually occurred. Server balances and revision checks remain authoritative.")
            OutlinedTextField(password, { password = it }, label = { Text("Confirm operator password") }, visualTransformation = PasswordVisualTransformation(), keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Password, autoCorrectEnabled = false), singleLine = true, modifier = Modifier.fillMaxWidth())
            Button(onClick = {
                try {
                    val cash = kind in listOf("DEPOSIT", "WITHDRAWAL")
                    if (cash) require(amount.toBigDecimal().signum() > 0) else {
                        require(market != null && quantity.toBigDecimal().signum() > 0 && price.toBigDecimal().signum() > 0 && fee.toBigDecimal().signum() >= 0)
                    }
                    val body = buildJsonObject {
                        put("entry_id", entryId); put("entry_type", kind); put("expected_revision", portfolio.revision)
                        put("occurred_at", occurredAt)
                        if (cash) put("cash_amount", amount) else {
                            put("market_id", market!!.market_id); put("quantity", quantity); put("unit_price", price); put("fee", fee)
                        }
                    }
                    val confirmation = jsonBody("password" to password); password = ""
                    vm.mutate({ it.stepUp(confirmation); it.recordEntry(portfolio.portfolio_id, body); Unit }) {
                        vm.loadPortfolios(); refresh(); amount = ""; quantity = ""; price = ""
                        entryId = UUID.randomUUID().toString(); occurredAt = Instant.now().toString()
                    }
                } catch (_: Exception) { vm.message.value = "Use positive finite decimal amounts, a registered market and a non-negative fee." }
            }, enabled = !busy && !offline && password.isNotEmpty()) { Text("Confirm manual record on server") }
            Note("Stable entry ID: $entryId. On connection loss, refresh the ledger before changing this draft. No automatic financial retries.")
        }
        var showHistory by rememberSaveable { mutableStateOf(false) }
        TextButton(onClick = { showHistory = !showHistory }) { Text("${if (showHistory) "Hide" else "Show"} transactions & intelligence") }
        if (showHistory) {
            ResourceStatus(resources["$key:entries"]); Record(resources["$key:entries"]?.value)
            ResourceStatus(resources["$key:intelligence"]); Record(resources["$key:intelligence"]?.value)
        }
    }
}
