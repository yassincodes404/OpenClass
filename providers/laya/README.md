# OpenClass Laya Provider

`openclass-provider-laya` is the default local decision provider adapter for OpenClass.
It connects OpenClass to the [Laya](https://github.com/NandhaKishorM/laya) System 1 decision engine.

## Features

- **Local & Free:** Runs locally on CPU/GPU without external API keys or subscription requirements.
- **Provider-Neutral:** Implements `openclass_core.providers.DecisionProvider`.
- **Permanent UNKNOWN:** Preserves explicit OpenClass UNKNOWN semantics and leaves supervision decisions to OpenClass.
- **Independent Profile:** Operates with its own `LayaProfile` without borrowing Jev-specific empirical assumptions.
- **Flexible Modes:** Supports local in-process `Router`, local HTTP daemon (`laya-serve`), or embedded fallback engine.
