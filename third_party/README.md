# Third-party sources

This directory holds pinned external sources. It contains exactly one entry.

## `third_party/iotauth`

The Secure Swarm Toolkit (SST) reference implementation, tracked as a Git
submodule pinned to one commit by this repository. It is the only copy of
IoTAuth used here. `make setup` installs its Python entity API directly from
`third_party/iotauth/entity/python`, and `make build-auth` builds Auth from
`third_party/iotauth/auth`.

Initialize it after cloning:

```bash
git submodule update --init third_party/iotauth
```

Generated credentials, keys, Auth databases, and entity configuration files are
written under the gitignored `runtime/sst/` directory, never into this
submodule. `make doctor` checks that the submodule is present at the recorded
commit and that its public API imports.

Upstream project: <https://github.com/iotauth/iotauth> (BSD-2-Clause). See
[../THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
