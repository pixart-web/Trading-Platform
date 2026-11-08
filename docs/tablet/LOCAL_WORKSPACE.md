# Local workspace

The release launcher now opens a native local workspace without a server URL, operator login or Pocket Alpha backend. Hilt injects the singleton financial database/ledger and public-data adapter. Financial computations remain independent of Compose; presentation is owned by LocalWorkspaceModel. The encrypted financial journal and public-history cache are separate databases.

Overview, historical Analyze (qualified SMA/EMA only), manual PAPER experiments, history and portable backup/settings are implemented. Wide windows use a persistent sidebar and adaptive grid. The optional server client is isolated behind Settings, has a return-to-local action and retains separate debug entry/tests. Default startup cancels the old server-cache worker; public-data failure does not turn into mandatory server login.

On restart, available public-data experiments are reconciled before display. Undecryptable experiments are preserved and reported; no replacement balance is invented. Account selection is currently the first readable public experiment, not a persisted last-selected preference. Each account is restricted to one EUR-quoted market and one pending order. Separate experiments do not share capital and must not be presented as a consolidated portfolio.

Build using the JDK21/SDK36 instructions in android/README.md. The debug APK is app/build/outputs/apk/debug/app-debug.apk. Production signing, complete tablet UX, biometric gating and physical qualification remain incomplete. This application slice replaces the earlier harness-only entry, but does not establish full product acceptance.
