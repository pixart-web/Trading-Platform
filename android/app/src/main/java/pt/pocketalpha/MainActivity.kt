package pt.pocketalpha

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.*
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import pt.pocketalpha.feature.*

@AndroidEntryPoint open class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        setContent { PocketTheme {
            var legacy by rememberSaveable { mutableStateOf(intent.getBooleanExtra("legacyClient", false)) }
            if (legacy) Column(Modifier.fillMaxSize()) {
                TextButton(onClick = { legacy = false }) { Text("Return to local workspace") }
                Box(Modifier.weight(1f)) { PocketApplication() }
            } else pt.pocketalpha.workspace.LocalWorkspaceScreen(onServerClient = { legacy = true })
        } }
    }
}
val Modules = linkedMapOf("watchlists" to "Watchlists", "intelligence" to "Market Intelligence",
    "forecasts" to "Forecasts", "fundamentals" to "Fundamentals", "derivatives" to "Derivatives Intelligence",
    "news" to "News / Sentiment / Macro", "backtesting" to "Backtesting", "research" to "Research Factory",
    "strategies" to "Strategies", "paper" to "Paper Trading", "risk" to "Risk", "execution" to "Execution",
    "autopilot" to "Autopilot", "reports" to "Reports", "settings" to "Settings", "system" to "System Health")

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun PocketApplication(vm: WorkspaceViewModel = hiltViewModel()) {
    val authenticated by vm.authenticated.collectAsStateWithLifecycle()
    val message by vm.message.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val tablet = with(LocalDensity.current) { LocalWindowInfo.current.containerSize.width.toDp() >= 840.dp }
    val drawer = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val destination = entry?.destination?.route ?: "dashboard"
    fun navigate(route: String) { nav.navigate(route) {
        popUpTo(nav.graph.findStartDestination().id) { saveState = true }
        launchSingleTop = true; restoreState = true
    } }
    Surface(Modifier.fillMaxSize(), color = Base) {
        when (authenticated) {
            null -> Box(Modifier.fillMaxSize(), contentAlignment = androidx.compose.ui.Alignment.Center) { CircularProgressIndicator() }
            false -> LoginScreen(vm)
            true -> ModalNavigationDrawer(drawerState = drawer, drawerContent = {
                ModalDrawerSheet {
                    Text("Pocket Alpha", Modifier.padding(24.dp), style = MaterialTheme.typography.headlineSmall)
                    LazyColumn { items(Modules.entries.toList()) { (route, title) ->
                        NavigationDrawerItem(label = { Text(title) }, selected = destination == route,
                            onClick = { navigate(route); scope.launchClose(drawer) }, modifier = Modifier.padding(horizontal = 12.dp))
                    } }
                }
            }) {
                Row(Modifier.fillMaxSize().testTag("adaptive-workspace")) {
                if (tablet) Surface(Modifier.width(232.dp).fillMaxHeight(), color = Panel) {
                    Column(Modifier.padding(12.dp).testTag("tablet-sidebar")) {
                        Text("POCKET ALPHA", Modifier.padding(12.dp), color = Accent,
                            style = MaterialTheme.typography.titleMedium)
                        Text("Connected workspace", Modifier.padding(horizontal = 12.dp),
                            color = Muted, style = MaterialTheme.typography.labelSmall)
                        HorizontalDivider(Modifier.padding(vertical = 16.dp), color = Border)
                        LazyColumn(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            items((linkedMapOf("dashboard" to "Dashboard", "analyze" to "Analyze",
                                "scanner" to "Scanner", "portfolio" to "Portfolio") + Modules).entries.toList()) { (route, title) ->
                                NavigationDrawerItem(label = { Text(title) }, selected = destination == route,
                                    onClick = { navigate(route) })
                            }
                        }
                    }
                }
                Scaffold(modifier = Modifier.weight(1f), containerColor = Base, topBar = {
                    TopAppBar(title = { Column { Text("POCKET ALPHA", style = MaterialTheme.typography.titleMedium)
                        Text("${Modules[destination] ?: destination.replaceFirstChar { it.uppercase() }} · server workspace",
                            style = MaterialTheme.typography.labelSmall, color = Muted) } },
                        navigationIcon = { if (!tablet) IconButton(onClick = { scope.launchOpen(drawer) }) { Icon(Icons.Default.Menu, "Open modules") } })
                }, bottomBar = {
                    if (!tablet) NavigationBar(containerColor = Panel) {
                        listOf("dashboard" to Icons.Default.Home, "analyze" to Icons.Default.Search,
                            "scanner" to Icons.Default.FilterList, "portfolio" to Icons.Default.AccountBalanceWallet,
                            "more" to Icons.Default.MoreHoriz).forEach { (route, icon) ->
                            NavigationBarItem(selected = destination == route, onClick = { navigate(route) },
                                icon = { Icon(icon, null) }, label = { Text(route.replaceFirstChar { it.uppercase() }) })
                        }
                    }
                }) { padding ->
                    Column(Modifier.padding(padding).fillMaxSize()) {
                        if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                        message?.let { text ->
                            Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
                                Text(text, Modifier.weight(1f), color = Amber, style = MaterialTheme.typography.bodySmall)
                                TextButton(onClick = { vm.message.value = null }) { Text("Dismiss") }
                            }
                        }
                        NavHost(navController = nav, startDestination = "dashboard", modifier = Modifier.weight(1f)) {
                            composable("dashboard") { DashboardScreen(vm, false) { navigate("chart") } }
                            composable("analyze") { DashboardScreen(vm, true) { navigate("chart") } }
                            composable("chart") { DashboardScreen(vm, false, fullChart = true) { nav.popBackStack() } }
                            composable("scanner") { ScannerScreen(vm) }
                            composable("portfolio") { PortfolioScreen(vm) }
                            composable("more") { LazyColumn(modifier = Modifier.testTag("module-list"), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                items(Modules.entries.toList()) { (route, title) -> OutlinedButton(onClick = { navigate(route) }, modifier = Modifier.fillMaxWidth()) { Text(title) } }
                            } }
                            Modules.forEach { (route, _) -> composable(route) {
                                when (route) {
                                    "watchlists" -> WatchlistsScreen(vm)
                                    "settings" -> SettingsScreen(vm)
                                    "forecasts", "intelligence" -> DashboardScreen(vm, true) { navigate("chart") }
                                    else -> AdvancedScreen(vm, route)
                                }
                            } }
                        }
                    }
                }
                }
            }
        }
    }
}
private fun kotlinx.coroutines.CoroutineScope.launchOpen(drawer: DrawerState) { this.launch { drawer.open() } }
private fun kotlinx.coroutines.CoroutineScope.launchClose(drawer: DrawerState) { this.launch { drawer.close() } }

@Composable private fun LoginScreen(vm: WorkspaceViewModel) {
    val stored by vm.origin.collectAsStateWithLifecycle()
    var server by remember(stored) { mutableStateOf(stored) }
    var username by rememberSaveable { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    val busy by vm.busy.collectAsStateWithLifecycle()
    val message by vm.message.collectAsStateWithLifecycle()
    LazyColumn(modifier = Modifier.testTag("login-list"), contentPadding = PaddingValues(24.dp), verticalArrangement = Arrangement.spacedBy(20.dp)) {
        item { Spacer(Modifier.height(40.dp)); Text("POCKET\nALPHA", color = Accent, style = MaterialTheme.typography.displayMedium) }
        item { Text("Your intelligence workspace", style = MaterialTheme.typography.titleLarge); Note("Connect to your private Pocket Alpha backend.") }
        item { OutlinedTextField(server, { server = it }, label = { Text("HTTPS server origin") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
        item { OutlinedTextField(username, { username = it }, label = { Text("Operator login") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
        item { OutlinedTextField(password, { password = it }, label = { Text("Password") }, visualTransformation = PasswordVisualTransformation(), keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Password, autoCorrectEnabled = false), singleLine = true, modifier = Modifier.fillMaxWidth()) }
        item { Button(onClick = { vm.login(server, username, password); password = "" }, enabled = !busy && server.isNotBlank() && username.isNotBlank() && password.isNotEmpty(), modifier = Modifier.fillMaxWidth()) { Text(if (busy) "Signing in…" else "Sign in securely") } }
        message?.let { item { Note(it, true) } }
        item { Note("Private operator access · TLS verification enabled\nReal-money trading is not authorized.") }
    }
}
