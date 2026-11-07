plugins { id("com.android.application"); id("com.chaquo.python") }
android {
    namespace = "pt.pocketalpha.runtimeproof"
    compileSdk = 36
    defaultConfig {
        applicationId = "pt.pocketalpha.runtimeproof"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.0.1-experiment"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }
}
chaquopy {
    defaultConfig {
        version = "3.12"
        if (!providers.gradleProperty("probeStdlibOnly").isPresent) {
            pip { install("pydantic==2.13.5"); install("pydantic-core==2.46.5") }
        }
    }
}
