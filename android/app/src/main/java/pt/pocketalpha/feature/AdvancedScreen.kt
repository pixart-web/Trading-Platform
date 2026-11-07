package pt.pocketalpha.feature

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import pt.pocketalpha.Modules
import pt.pocketalpha.core.*
import java.time.Instant
import java.util.UUID

@Composable fun AdvancedScreen(vm: WorkspaceViewModel, route: String) {
    val resources by vm.resources.collectAsStateWithLifecycle()
    val selected by vm.selected.collectAsStateWithLifecycle()
    var identifier by rememberSaveable(route) { mutableStateOf("") }
    var secondary by rememberSaveable(route) { mutableStateOf("") }
    var type by rememberSaveable(route) { mutableStateOf("reports") }
    val key = "advanced:$route"
    fun load() {
        try {
            val now = Instant.now().toString()
            when (route) {
                "strategies" -> vm.document(key, "api/v1/strategies")
                "paper" -> vm.document(key, "api/v1/paper/accounts")
                "fundamentals" -> selected?.let { vm.document(key, "api/v1/assets/${safeId(it.asset_id)}/fundamentals", mapOf("as_of" to now)) }
                "news" -> vm.document(key, "api/v1/context/${safeId(identifier.ifBlank { selected?.asset_id ?: "" })}", mapOf("as_of" to now))
                "derivatives" -> selected?.let { market ->
                    when (type) {
                        "context" -> vm.document(key, "api/v1/derivatives/${safeId(identifier)}/context", mapOf("as_of" to now))
                        "option-skew" -> vm.document(key, "api/v1/derivatives/option-skew", mapOf("as_of" to now, "call_contract_id" to safeId(identifier), "put_contract_id" to safeId(secondary)))
                        else -> vm.document(key, "api/v1/derivatives/$type", mapOf("as_of" to now,
                            "underlying_asset_id" to market.asset_id, "venue_id" to market.venue_id))
                    }
                }
                "backtesting" -> vm.document(key, "api/v1/backtests/${UUID.fromString(identifier)}")
                "research", "reports" -> vm.document(key, "api/v1/research/$type/${UUID.fromString(identifier)}")
                else -> vm.document(key, "api/v1/status")
            }
        } catch (_: IllegalArgumentException) { vm.message.value = "Enter the required valid server identifier." }
    }
    LaunchedEffect(route) {
        if (route in listOf("strategies", "paper", "risk", "execution", "autopilot", "system")) load()
        if (route == "derivatives") type = "contracts"
    }
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Text(Modules[route] ?: route, style = MaterialTheme.typography.headlineMedium) }
        if (route in listOf("fundamentals", "derivatives", "news")) item { MarketPicker(vm) }
        if (route in listOf("research", "reports")) item { Choice("Artifact", listOf("reports", "models"), type) { type = it } }
        if (route == "derivatives") item { Choice("Evidence", listOf("contracts", "term-structure", "option-skew", "context"), type) { type = it } }
        if (route in listOf("backtesting", "research", "reports", "news") || (route == "derivatives" && type in listOf("context", "option-skew"))) item {
            OutlinedTextField(identifier, { identifier = it.take(128) }, label = { Text(when (route) {
                "news" -> "Context entity ID (defaults to selected asset)"
                "derivatives" -> if (type == "option-skew") "Call contract ID" else "Contract ID"
                else -> "Existing server artifact UUID"
            }) }, modifier = Modifier.fillMaxWidth())
        }
        if (route == "derivatives" && type == "option-skew") item {
            OutlinedTextField(secondary, { secondary = it.take(128) }, label = { Text("Put contract ID") }, modifier = Modifier.fillMaxWidth())
        }
        item {
            when (route) {
                "backtesting", "research", "reports" -> Note("Existing server artifacts only. The backend has no durable submission/job-status API; creating research jobs from Android is not implemented.", true)
                "risk", "execution", "autopilot" -> Note("Current operational state is not exposed by a safe client monitoring contract. Internal journals and operator control interfaces remain private. Live trading is not authorized.", true)
                "paper" -> Note("PAPER balances, orders, fills, fees and reconciliation only. The server runs the existing simulation engine; Android never simulates fills.")
                "strategies" -> Note("Versioned server strategy catalog and lifecycle evidence. Mobile cannot promote a strategy or authorize trading.")
                "system" -> Note("Authenticated native API capabilities. Deployment and provider degradation must be resolved on the server.")
                "fundamentals" -> Note("Publication, availability and revision timestamps remain visible. Unsupported assets return unavailable.")
                "derivatives" -> Note("Descriptive stored contract observations. No derivatives execution authority.")
                "news" -> Note("Stored news, normalized sentiment and macro observations with causal timestamps; no invented provider feed.")
            }
            Button(onClick = { load() }, enabled = resources[key]?.loading != true) { Text("Load server evidence") }
        }
        item { PocketCard("Server records") {
            ResourceStatus(resources[key]); Record(resources[key]?.value)
        } }
    }
}

@Composable fun SettingsScreen(vm: WorkspaceViewModel) {
    val resources by vm.resources.collectAsStateWithLifecycle()
    val origin by vm.origin.collectAsStateWithLifecycle()
    var notificationMessage by remember { mutableStateOf<String?>(null) }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        notificationMessage = if (it) "Notification permission granted. Remote delivery is not configured." else "Notification permission declined."
    }
    LaunchedEffect(Unit) { vm.document("sessions", "api/v1/auth/sessions") }
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { Text("Settings & identity", style = MaterialTheme.typography.headlineMedium) }
        item { PocketCard("Private workspace") { Text(origin); Note("Change servers by signing out first. Tokens are encrypted with an Android Keystore key; access credentials remain in memory.")
            Button(onClick = vm::logout) { Text("Revoke this session & sign out") }
        } }
        item { PocketCard("Devices & sessions") {
            val sessions = resources["sessions"]
            ResourceStatus(sessions)
            sessions?.value.elements().forEach { session ->
                Text(session.text("device_name") ?: "Device", style = MaterialTheme.typography.titleSmall)
                Note("Created ${session.text("created_at")} · last refresh ${session.text("last_seen_at")}")
                Note("Expires ${session.text("expires_at")}")
                TextButton(onClick = {
                    val id = session.text("session_id") ?: return@TextButton
                    if (session.text("current") == "true") vm.logout() else vm.mutate({ it.revoke(id) }) {
                        vm.document("sessions", "api/v1/auth/sessions")
                    }
                }, enabled = sessions?.offline != true) { Text(if (session.text("current") == "true") "Sign out this device" else "Revoke device") }
            }
        } }
        item { PocketCard("Notifications") {
            Note("Channels: Research, Risk, Paper, System. Remote push requires a delivery provider and device registration; it is not operational in this build.", true)
            Button(onClick = {
                if (Build.VERSION.SDK_INT >= 33) permission.launch(Manifest.permission.POST_NOTIFICATIONS)
                else notificationMessage = "This Android version uses notification channel settings."
            }) { Text("Allow advisory notifications") }
            notificationMessage?.let { Note(it) }
        } }
        item { PocketCard("Offline & financial safety") {
            Note("Cached views are labelled stale and are read-only. No offline financial commands or broker credentials are stored. Server processes continue independently when this app closes.")
            Note("Real-money trading is not authorized. This build is an integration candidate, not a production-parity release.", true)
        } }
    }
}
