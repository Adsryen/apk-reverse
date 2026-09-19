# Ad removal

Goal: ads stop appearing, and **nothing else breaks**. Read `references/pitfalls.md` P5 and P6 before patching anything here.

## Step 1: identify which ads exist and who owns them

Do not assume "ads" is one thing. Enumerate first.

**SDK-integrated ads** (the app calls an SDK):
- Search dex strings for SDK markers: `openadsdk`, `TTAdSdk`, `TTAdNative`, `Pangle`, `pangolin`, `com.qq.e`, `GDTAd`, `gdt_plugin`, `anythink`, `ATSDK`, `ATRewardVideoAd`, `bdxadsdk`, `sigmob`, `ksad`, `mobads`, `beizi`.
- **Aggregators** (AnyThink, TopOn, and similar) are wrappers: the visible ad networks underneath are *their* adapters, not app code. Patching an individual network's class is usually pointless — the aggregator still runs and still reaches the network.
- The app almost always funnels every call through **one wrapper class**. Find it; that is your patch surface.

**Server-driven ads / sponsored content** (the server returns the ad, the client renders it):
- Look for endpoints like `/adverts`, `/adv`, `/banner`, `/config`, and DTOs named `Advertisement*`, `Advert*`, `Banner*`, `Promotion*`.
- The client renders whatever the list contains. If the list is empty there is nothing to show — but see `references/pitfalls.md` P5 on **how not** to empty it.
- Sponsored cards that look like content (a VPN promo, a network-accelerator card, a third-party product) are usually exactly this.

**Legit content that looks like an ad.** Verify before acting. A `/adverts?position=banner` response containing anime titles and poster images is the home-page carousel, not an advertisement. Removing it removes real functionality.

## Step 2: map the wrapper

Find the app's own helper and enumerate its public surface. Typical shape:

```
helper.init(Application)              -> Sdk.init(appId, appKey); Sdk.start()
helper.showSplash(Activity, ViewGroup, onClose: () -> Unit)
helper.showInterstitial(Activity)
helper.showReward(Activity, onStart: () -> Unit, onFinish: (Boolean) -> Unit)
helper.preload*(Activity)
helper.canShow*(Activity): Boolean
```

Read each method body and classify:

| Method | Contains | Safe patch |
|---|---|---|
| Init | `Sdk.init(...)` + `Sdk.start()` | Replace body with `return-void` |
| Show splash/interstitial | constructs an ad object, `loadAd()` / `show()` | Replace body, **but must still invoke the completion callback** |
| Show reward | same, plus success/failure lambdas | Replace body; decide deliberately whether to grant the reward |
| Preload/warm-up | `RewardVideoAutoAd.init(...)` | `return-void` |
| Gate check | `isAdReady`, `canShow` | return `false` / `0` |

### The callback trap (this one breaks startup)

A splash/loading ad usually takes a **completion lambda** as a parameter. The app's startup state machine waits for that lambda before it dismisses the splash screen.

**If you replace the method with a bare `return-void`, the lambda never fires, and the app hangs forever on the splash screen.**

Correct shape — skip the ad, still complete:

```
.method public final showSplash(Landroid/app/Activity;Landroid/view/ViewGroup;Lkotlin/jvm/functions/Function0;)V
    .registers N
    invoke-interface {p3}, Lkotlin/jvm/functions/Function0;->invoke()Ljava/lang/Object;
    return-void
.end method
```

**Before patch, prove the contract.** Read the listener class the method constructs and find which callback triggers the completion lambda (`onAdDismiss`? `onAdError`? `onAdLoadTimeout`?). Only that tells you whether to call it on success, failure, or unconditionally.

For a reward ad whose lambdas are `(onStart, (Boolean) -> Unit)`, granting the reward client-side is a choice: `onFinish(true)` will make the app treat the reward as earned. Check whether the reward is validated server-side before promising it.

## Step 3: choose the patch layer

From safest to riskiest (see `references/dex-patching.md` for the full table):

1. **Kill SDK init** — the SDK never starts; its networks are never contacted. Highest-value single patch. Verify nothing else depends on the SDK being initialized.
2. **No-op the show/preload methods** — preserving callbacks.
3. **Neutralize the gate** — `isAdReady`/`canShow` return false.
4. **Filter server-issued ad data at the consumption layer** — drop entries for the target position before they reach UI state.
5. *(avoid)* **Renderer-level suppression** — only if the component is genuinely ad-exclusive. Check `references/pitfalls.md` P6 first.
6. *(avoid)* **Transport-level blocking** — see `references/pitfalls.md` P5.

## Step 4: verify — and verify it properly

Logcat silence alone is weak evidence. Use several independent signals:

1. **Process stays alive** through startup and across a few screens; no `FATAL EXCEPTION`, no `VerifyError`, no `uncaughtException`.
2. **SDK log keywords absent** — `anythink`, `ATSDK`, `Pangle`, `TTAd`, `GDT`, etc. should not appear at all.
3. **DNS / socket level (strongest, and cheap)** — hook or observe name resolution. If the ad SDK's network stack is initialized it will resolve its own domains. Many ad SDKs **bypass the system proxy**, so proxy logs may miss them; a runtime `InetAddress` hook does not.
   - Before: a burst of ad/tracker domains.
   - After: **none at all** — meaning the init path never ran, not merely "shown but not rendered".
4. **Exercise the screens that had ads** — splash, home banner, detail page, player, reward button.
5. **Confirm nothing unrelated regressed** — images load, video plays, lists scroll, login works.

A useful framing for the report: distinguish *"the ad was hidden"* from *"the ad subsystem never started"*. The second is a much stronger claim, and DNS/socket evidence can prove it.

## Step 5: what is usually NOT removable

Be honest about residual ads rather than breaking the app to chase them:

- **Server-driven content promos** deep in a feature's own data payload, where the screen's load depends on the same request. Suppressing them requires a data-consumption patch, not transport blocking.
- **Ads delivered as content** (a sponsored "article" or a native card with no SDK marker) — indistinguishable from real content without runtime tracing.
- **Ads whose SDK init also enables other features.** Removing init can break functionality that silently depended on it.

If a residual ad cannot be removed without breaking something, say so, and say exactly which coupling caused it. That is a better deliverable than a broken APK.
