# MAPNET MOBILE — Règles ProGuard/R8 (build release minifié).
# Objectif : réduire la taille sans casser les ponts JNI des plugins natifs.

# --- Flutter engine ---
-keep class io.flutter.** { *; }
-keep class io.flutter.plugins.** { *; }
-keep class io.flutter.embedding.** { *; }
-dontwarn io.flutter.embedding.**

# --- Play Core (deferred components) : non utilisé mais référencé par Flutter.
# On ignore les classes absentes plutôt que d'ajouter la lib (inutile ici).
-dontwarn com.google.android.play.core.**
-keep class com.google.android.play.core.** { *; }

# --- Geolocator (accès GPS natif) ---
-keep class com.baseflow.geolocator.** { *; }
-dontwarn com.baseflow.geolocator.**

# --- permission_handler (permissions runtime) ---
-keep class com.baseflow.permissionhandler.** { *; }
-dontwarn com.baseflow.permissionhandler.**

# --- sqflite (SQLite natif) ---
-keep class com.tekartik.sqflite.** { *; }
-dontwarn com.tekartik.sqflite.**

# --- path_provider ---
-keep class io.flutter.plugins.pathprovider.** { *; }

# Conserver les annotations et les classes appelées par réflexion.
-keepattributes *Annotation*
-keepattributes Signature
-keepattributes Exceptions

# Ne pas avertir sur les dépendances optionnelles absentes.
-dontwarn javax.annotation.**
