# Runtime data — DataStore, SharedPreferences, SQLite, protobuf

Sometimes the cheapest fix is not code at all, but a value in app data. And sometimes that is exactly the wrong fix, because it does not survive a fresh install (`pitfalls.md` P11).

## Decide first: data or code?

| Question | Answer |
|---|---|
| Does the deliverable need to work after a clean install? | Then it must be **code**, not data |
| Are you iterating on your own device? | Data edits are a fast way to test a hypothesis **before** writing the patch |
| Is the value written by the app itself (a token, a cache, a counter)? | Data — and the server may re-assert it |

**Recommended workflow:** use a data edit to *prove the hypothesis* (cheap), then implement the same effect in code (durable), then verify with a clean install.

## Where app data lives

```
/data/data/<pkg>/                     (== /data/user/0/<pkg>)
├── files/
│   ├── datastore/*.preferences_pb    AndroidX DataStore (protobuf)
│   └── ...
├── shared_prefs/*.xml                SharedPreferences
├── databases/*.db                    SQLite (Room, etc.)
└── <sdk caches>/                     crash logs, download state, ad configs
```

Read with root:
```bash
adb shell "su -c 'ls -la /data/data/<pkg>/files/datastore/'"
adb shell "su -c 'xxd /data/data/<pkg>/files/datastore/<name>.preferences_pb | head -20'"
```

## AndroidX DataStore (protobuf)

Format:
```proto
PreferenceMap { map<string, Value> preferences = 1; }
Value {
  oneof value {
    bool boolean = 1; float float = 2; int32 integer = 3; int64 long = 4;
    string string = 5; StringSet string_set = 6; double double = 7; bytes bytes = 8;
  }
}
```

**Encoding an entry requires TWO tag levels:**
```
outer (map field 1, wire type 2) : 0A <len(inner)>
inner (one map entry)            : 0A <len(key)> <key>  12 <len(value)> <value>
value payload (e.g. int64)       : 20 <varint>        # field 4, wire type 0
value payload (e.g. int32)       : 18 <varint>        # field 3, wire type 0
value payload (e.g. bool)        : 08 <0x00|0x01>     # field 1, wire type 0
value payload (e.g. string)      : 2A <len> <utf8>    # field 5, wire type 2
```

Omitting the **outer** tag produces a file the app cannot deserialize, and the failure is usually a **stack-less crash** (`pitfalls.md` P8). Use `scripts/datastore_inject.py` rather than hand-rolling it.

Procedure:
1. `am force-stop <pkg>` (DataStore caches in memory and writes back)
2. Write the file (as root), preserving ownership — `cp -f` over the existing file keeps its owner
3. `restorecon` if SELinux is enforcing
4. Start the app and observe

Verify by reading the file back with `xxd` before launching.

## SharedPreferences (XML)

Simple XML. Edit with the app stopped. Types are explicit (`<boolean>`, `<int>`, `<long>`, `<string>`). Same ownership rules.

## SQLite

```bash
adb shell "su -c 'sqlite3 /data/data/<pkg>/databases/<db>.db \".tables\"'"
adb shell "su -c 'sqlite3 ... \"select * from <table> limit 5;\"'"
```
Useful for: auth sessions (tokens), user profile caches (often a raw JSON blob), and any server state the app persists. A JSON column often contains the exact server payload — the fastest way to learn field names.

## Ownership — the silent killer

The app runs as its own uid. A file written by root with the wrong owner is unreadable, and directory permissions are `drwx------`.

```bash
uid=$(adb shell "dumpsys package <pkg> | grep userId=" | tr -dc '0-9')
adb shell "su -c 'chown -R $uid:$uid /data/user/0/<pkg>'"
adb shell "su -c 'restorecon -R /data/user/0/<pkg>'"
```
Symptom of getting this wrong: crash in a database-init path right after launch, often `Cannot open database ... Directory ... doesn't exist`.

Note: after every reinstall the app's uid **increments**, so a restored data directory needs this again.

## Introducing a value that does not exist yet

If the key is absent, the app uses a default. Two options:

1. **Add the key** with the exact protobuf shape above.
2. **Confirm the default first** — sometimes removing a key already yields the behavior you want (e.g. clearing an expiry so it reads as "not set").

## Making the fix durable

If the effect must ship inside an APK, move it into code. Patterns, in order of preference:

- **Patch the read path** so the value is always the desired one. Find where the Flow/getter is built and make it emit a constant.
- **Patch the decision**, not the data: find the comparison that consumes the value and make it resolve the way you want.
- **Do not patch the generic encoder/boxer** used by the whole app (`pitfalls.md` P6).

Reference case: a promo popup was gated by `<key>_expires_at`. Writing a large value via DataStore suppressed it on the test device, but a fresh install lost it. The durable fix replaced the dedicated map-lambda that produces the value so it always yields a far-future timestamp — a single-purpose class, safe to patch, no effect on the shared serialization helpers.

## Cautions

- Editing data while the app is running is unreliable: in-memory caches win.
- The server may overwrite your value on next sync. If the app re-fetches and re-persists the authoritative value, a data edit is temporary by design — which is exactly why the durable version belongs in code.
- Do not edit a token you do not own and expect it to be accepted; tokens are validated server-side (`references/server-api.md`).
