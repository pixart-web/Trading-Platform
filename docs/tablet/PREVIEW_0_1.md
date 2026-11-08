# Pocket Alpha Tablet — Preview 0.1

Preview debug para testes manuais no Redmi Pad 2. Sem Play Store, sem backend Pocket Alpha e sem trading real. O Autopilot não está validado nem disponível nesta versão.

[Descarregar APK](https://github.com/pixart-web/Trading-Platform/releases/download/tablet-preview-0.1/pocket-alpha-tablet-preview-0.1-debug.apk) · [Pré-release e checksums](https://github.com/pixart-web/Trading-Platform/releases/tag/tablet-preview-0.1)

## Instalar no tablet

1. Abrir o link da APK no navegador do Redmi Pad 2 e descarregar o ficheiro.
2. Abrir o ficheiro em Downloads. Se o Android pedir autorização para instalar a partir deste navegador/gestor de ficheiros, permitir essa origem e voltar à instalação.
3. Tocar em **Instalar** e depois em **Abrir**. Deve aparecer **Local workspace** e **Pocket Alpha Tablet — Preview 0.1**, sem pedido de login ou URL de servidor.
4. Ligar o tablet à Internet para consultar os dados públicos. O Mac, Hetzner e qualquer servidor Pocket Alpha podem permanecer desligados. Sem Internet, os dados anteriores são identificados como cache/desligado.
5. Em PAPER, criar uma experiência com 1.000 EUR virtuais. Em Backup & Settings, exportar uma cópia cifrada com palavra-passe própria.

É uma APK debug assinada, não uma versão de produção. Se já existir outra APK com assinatura diferente, o Android recusará a atualização: exportar primeiro os backups cifrados antes de ponderar desinstalar, pois a desinstalação elimina os dados e a chave local. Nunca desinstalar para resolver uma atualização sem preservar as experiências. A assinatura desta pré-release é independente das assinaturas debug temporárias do CI.

## Conteúdo e limites

Inclui workspace local, candles H1 reais BTC-EUR/ETH-EUR, gráfico histórico, SMA/EMA qualificados, experiências PAPER manuais separadas, saldos/histórico autoritativos e backup/restauro AES-GCM com chave derivada de palavra-passe. Consulta apenas endpoints públicos GET; não inclui credenciais de exchange nem dispatch de ordens reais.

Não inclui Autopilot funcional, estratégia nativa completa, carteira multi-posição com caixa comum, mudança de dia UTC, biometria ou aceitação física. Uma experiência pode ser interrompida pelo limite de dia UTC: conservar o histórico e criar outra, sem apagar dados. Fills automáticos, rentabilidade, probabilidades calibradas e execução contínua não são prometidos.

APK universal: `arm64-v8a`, `armeabi-v7a`, `x86`, `x86_64`; Android mínimo API 26 (8.0), target API 36; `pt.pocketalpha.android`, versionCode 2, versionName `0.1-preview`. O Redmi Pad 2 usa a plataforma [Xiaomi HyperOS 2](https://www.mi.com/sg/product/redmi-pad-2/specs/); o teste no aparelho específico continua pendente. A compatibilidade do pacote ARM64 e os testes em emulador não substituem essa aceitação.

SHA-256 da APK publicada:

```text
fec394af76b733d345d8640473ce7b71f430c8015edd26667984bf929a75a177
```

Certificado debug SHA-256: `f58359d1e34ae82c5f3528e22e6fc2ac4b18aabd361eb8869a8067df3e91b52f`.

## Compilar e verificar

A partir de `android/`, com JDK 21 e SDK/build-tools 36:

```sh
./gradlew --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleDebugAndroidTest :app:assembleRelease :app:bundleRelease
```

Saída instalável: `app/build/outputs/apk/debug/app-debug.apk`. Não passar `e2eCaFile` à build distribuída; só são confiadas as raízes TLS do sistema. A compilação local final terminou com `BUILD SUCCESSFUL`: 14 testes JVM passaram; lint, APK debug/test, APK release e AAB passaram. A assinatura v2 foi verificada por `apksigner verify --verbose --print-certs`; `aapt dump badging` confirmou label, versão, launcher e ABIs.

Emulador ARM64 API 35, 2560×1600: 3 testes passaram com dados públicos reais, incluindo arranque local com identificação Preview, criação PAPER de 1.000 EUR, SMA e restauro cifrado. Ruff check/format, mypy (272 ficheiros), golden Python e schema passaram. Pytest local: 1.097 passaram, 233 ignorados, 2 avisos; os testes com serviços e x86_64 são confirmados no CI do commit associado à tag antes da publicação. A release regista esse link e resultado final.

## Âmbito, arquitetura e ficheiros

Fase: empacotamento e distribuição da Preview operacional existente. Sem alteração ao motor financeiro, políticas económicas ou bases de dados; sem migrações. Mantém os limites e a dívida do [relatório operacional](OPERATIONAL_COMPLETION_REPORT.md). A continuação autorizada da estratégia nativa vem depois da entrega deste pacote, com testes oracle antes de permitir decisões automáticas; esta APK permanece congelada na sua tag.

Ficheiros alterados nesta entrega:

- `android/app/build.gradle.kts`: versão da Preview.
- `android/app/src/main/AndroidManifest.xml`: label por recurso.
- `android/app/src/main/res/values/strings.xml`: identificação da aplicação.
- `android/app/src/main/java/pt/pocketalpha/workspace/LocalWorkspaceScreen.kt`: identificação visível.
- `android/app/src/androidTest/java/pt/pocketalpha/PublicWorkspaceAndroidTest.kt`: verifica label, versão e arranque local.
- `docs/tablet/PREVIEW_0_1.md`: instalação, limites, build e verificação.
- `android/README.md`: acesso à distribuição de teste.
