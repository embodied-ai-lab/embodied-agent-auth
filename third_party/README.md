# Third-party sources

This directory holds pinned external sources. It contains exactly one entry.

## `third_party/iotauth`

`third_party/iotauth` is the lab's only IoTAuth/SST source. It is a pinned Git
submodule. `make setup` installs its Python entity API, and `make build-auth`
builds Auth from it.

Initialize it after cloning:

```bash
git submodule update --init third_party/iotauth
```

Generated credentials, keys, databases, and configs go under gitignored
`runtime/sst/`, never into this submodule. `make doctor` checks that the
dependency and public Python API are available.

Upstream project: <https://github.com/iotauth/iotauth> (BSD-2-Clause). See
[../THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
