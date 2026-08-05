# Contributing

Contributions are welcome under AGPL-3.0-only. Keep source layers explicit, preserve immutable provenance, and add fixtures for parser or reconciliation changes.

Before opening a pull request, run:

```bash
pnpm verify
pnpm test:e2e
```

Do not commit raw official downloads, cached originals, credentials, personal data, or large release artifacts. Use `data/manifests` only for small versioned manifests.
