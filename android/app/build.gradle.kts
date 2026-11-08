plugins {
    alias(libs.plugins.android)
    alias(libs.plugins.kotlin)
    alias(libs.plugins.compose)
    alias(libs.plugins.serialization)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
}
android {
    namespace = "pt.pocketalpha"
    compileSdk = 36
    defaultConfig {
        applicationId = "pt.pocketalpha.android"
        minSdk = 26
        targetSdk = 36
        versionCode = 2
        versionName = "0.1-preview"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    sourceSets.getByName("test").java.srcDir("src/sharedTest/java")
    sourceSets.getByName("androidTest").java.srcDir("src/sharedTest/java")
    buildFeatures { compose = true; buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    lint { abortOnError = true; warningsAsErrors = true }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }
}
dependencies {
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.preview)
    implementation(libs.compose.material)
    implementation(libs.compose.icons)
    implementation(libs.activity)
    implementation(libs.lifecycle)
    implementation(libs.viewmodel)
    implementation(libs.navigation)
    implementation(libs.hilt)
    implementation(libs.hilt.navigation)
    ksp(libs.hilt.compiler)
    implementation(libs.room)
    implementation(libs.room.ktx)
    ksp(libs.room.compiler)
    implementation(libs.datastore)
    implementation(libs.work)
    implementation(libs.serialization)
    implementation(libs.retrofit)
    implementation(libs.retrofit.json)
    implementation(libs.okhttp)
    testImplementation(libs.junit)
    testImplementation(libs.mockwebserver)
    testImplementation(libs.coroutines.test)
    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.compose.test)
    androidTestImplementation(libs.android.junit)
    androidTestImplementation(libs.test.runner)
    debugImplementation(libs.compose.tooling)
    debugImplementation(libs.compose.test.manifest)
}

dependencyLocking { lockAllConfigurations() }
tasks.register("writeRuntimeCoordinates") {
    val output = layout.buildDirectory.file("reports/runtime-coordinates.tsv")
    outputs.file(output)
    inputs.files(provider { configurations.getByName("releaseRuntimeClasspath") })
    doLast {
        val coordinates = configurations.getByName("releaseRuntimeClasspath").resolvedConfiguration
            .resolvedArtifacts.map { it.moduleVersion.id }.distinctBy { "${it.group}:${it.name}:${it.version}" }
            .sortedBy { "${it.group}:${it.name}" }.joinToString("\n") { "${it.group}:${it.name}\t${it.version}" }
        output.get().asFile.apply { parentFile.mkdirs(); writeText(coordinates + "\n") }
    }
}

// A disposable TLS root can be injected for instrumentation only. Standard debug and all
// release builds trust system roots exclusively; no certificate validation is bypassed.
val e2eResources = layout.buildDirectory.dir("generated/e2e/res")
val e2eCa = providers.gradleProperty("e2eCaFile")
val generateE2eTrust by tasks.registering {
    inputs.property("certificatePath", e2eCa.orElse(""))
    outputs.dir(e2eResources)
    doLast {
        val directory = e2eResources.get().asFile
        directory.deleteRecursively()
        directory.mkdirs()
        if (e2eCa.isPresent) {
            directory.resolve("raw/e2e_ca.pem").apply {
                parentFile.mkdirs(); writeBytes(file(e2eCa.get()).readBytes())
            }
            directory.resolve("xml/network_security_config.xml").apply {
                parentFile.mkdirs()
                writeText("""<network-security-config>
                    <base-config cleartextTrafficPermitted="false"><trust-anchors><certificates src="system" /></trust-anchors></base-config>
                    <domain-config cleartextTrafficPermitted="false"><domain>localhost</domain><trust-anchors><certificates src="@raw/e2e_ca" /></trust-anchors></domain-config>
                </network-security-config>""")
            }
        }
    }
}
android.sourceSets.getByName("debug").res.srcDir(e2eResources)
tasks.matching { it.name == "preDebugBuild" }.configureEach { dependsOn(generateE2eTrust) }

// Resolve the Linux CI tool on macOS when updating verification metadata.
tasks.register("resolveLinuxBuildTool") {
    doLast {
        configurations.detachedConfiguration(dependencies.create("com.android.tools.build:aapt2:8.9.2-12782657:linux"))
            .apply { isTransitive = false }.resolve()
    }
}

// Lint's UAST index sees Hilt sources from both variants. Avoid observing files while
// an included Hilt compiler is replacing them during a combined debug/release build.
tasks.matching { it.name.startsWith("lintAnalyze") || it.name.startsWith("lintVitalAnalyze") }
    .configureEach { mustRunAfter(tasks.matching { it.name.startsWith("hiltJavaCompile") }) }
