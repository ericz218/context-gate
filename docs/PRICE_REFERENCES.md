# Console public-price references

Checked on 2026-10-31. All rates below are USD per million tokens, in the order input / output / cache read. These are committed price snapshots, not a background price updater.

The console's “按官方标价 / Official price” comparison uses the manufacturer's public list price where verified. Open models without a manufacturer API price may use a clearly labelled hosting-provider reference. A hosting price is not a claim that the free/local route incurred that charge. “Configured cost” retains the user's existing free/paid rules. The raw token ledger is not rewritten.

## Vendor prices

- [Meta pricing](https://dev.meta.ai/docs/pricing-rate-limits): Muse Wonder 1.0 uses 4 / 20 / 0.20. Muse Spark 1.3, 1.2 and 1.1 Standard use 1.25 / 4.25 / 0.15. Spark 1.3 and 1.2 Contributor use 0.10 / 0.20 / 0.002, distinct from Standard. No long-context premium is listed. Search-tool charges are not included in token estimates.
- [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/): V4.1 Flash uses the peak reference 0.30 / 1.20 / 0.006. The vendor explicitly maps retired V4 Flash and V4 Flash Vision Exp IDs to V4.1 Flash. Off-peak and Chinese-holiday discounts are not applied; the UI identifies this peak-price comparison. It does not reconstruct historical invoices.
- [Inception Mercury 3 announcement](https://www.inceptionlabs.ai/blog/introducing-mercury-3): standard list 0.20 / 0.70 / 0.02. The limited-time 50% launch promotion is excluded from this standard-list comparison and is described in the UI.
- [QwenCloud Qwen3.8 27B](https://www.qwencloud.com/models/qwen3.8-27b): 0.50 / 3 / 0.10 using implicit cache reads. Explicit cache writes are 0.625. The ledger does not distinguish explicit and implicit reads, so the UI states the implicit-cache assumption rather than applying the lower explicit-read rate of 0.05.
- [QwenCloud Qwen3.8 Flash](https://www.qwencloud.com/models/qwen3.8-flash): 0.15 / 0.47 / 0.016, explicit writes 0.20. [The vendor's Flash-Next announcement](https://www.alibabacloud.com/blog/qwen3-8-flash-next-a-new-architecture-towardsultimate-cost-efficiency_603501) identifies Qwen3.8 Flash as the production service; the UI explicitly names this reference for Flash-Next. The current model price page takes precedence over the older announcement's 0.16 input rate.
- [Xiaomi's entry in the OpenRouter provider endpoint catalogue](https://openrouter.ai/api/v1/models/xiaomi/mimo-v2.6-flash/endpoints): MiMo V2.6 Flash 0.14 / 0.28 / 0.0028. This selects the Xiaomi provider entry, not the cheapest third-party host.
- [StepFun's entry in the OpenRouter provider endpoint catalogue](https://openrouter.ai/api/v1/models/stepfun/step-5-preview/endpoints): Step 5 Preview 1 / 2.70 / 0.10, selecting the StepFun provider entry.

## Clearly labelled provider references

These are individual published provider offers, with all rates taken from the same offer. A free `:free` endpoint still compares the underlying model with its paid reference when “Official price” is selected.

- [Nemotron 3 Ultra 550B A55B, DeepInfra standard offer](https://openrouter.ai/api/v1/models/nvidia/nemotron-3-ultra-550b-a55b/endpoints): 0.50 / 2.20 / 0.10. Flex-tier pricing is excluded.
- [Nemotron 3 Super 120B A12B, Crusoe](https://openrouter.ai/api/v1/models/nvidia/nemotron-3-super-120b-a12b/endpoints): 0.30 / 2.40 / 0.15.
- [Muse Glimmer 30B, DeepInfra](https://openrouter.ai/api/v1/models/meta/muse-glimmer-30b/endpoints): 0.30 / 1.20 / 0.04.
- [Qwen3 14B, OpenRouter published model reference](https://openrouter.ai/api/v1/models/qwen/qwen3-14b/endpoints): 0.12 / 0.24. No cache discount is listed for this reference, so cached input is compared at 0.12 rather than inventing a discount.

No separate discounted cache-creation price is assumed for vendors that do not publish one; creation tokens use ordinary input prices in these new rules.

## Unknown identities and missing sources

At verification, Hunyuan3, Longcat-2.5 and MiniCPM5-2B still lacked a verified exact-model per-token offer. The available LongCat page covers 2.0 and is not substituted for 2.5. Local `qwen14b`, Qwen2.5 Coder 7B/14B, Gemini Web's `gemini-argon`, `gpt-flash`, and `probe-mantle-*` are not silently mapped to nearby models. They retain token counts with an unpriced marker in the public-price comparison.

The new rules use an exact identity list. Known provider prefixes and `:free` may be removed for lookup; unknown versions, parameter sizes, and variants do not match by a broad family substring. Existing user `official_rules` retain precedence.
