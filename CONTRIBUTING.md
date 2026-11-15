# Contributing to esphome-matter

Contributions are welcome! Matter is pretty complex and there never is a single way to create a device type, cluster,
feature, etc... There's also not a single universal way to update an attribute, listen to an attribute update,
sending commands or events, etc... Once all of that has been implemented, the focus can shift more to actual device
type implementations.

You're welcome to implement support for specific device types and even create PRs for them, but since the things
mentioned above still have some rough edges, it might still take some time before your PR is merged.

Instead of implementing a new device type in C++ and python, you may also try to implement it in yaml inside the
`packages` directory. Not all actions and triggers have been implemented yet so not all behaviour can be implemented
that way yet. But the idea is to use actions such as `matter.set_attribute` and triggers such as `on_attribute` to
implement the behaviour.

At the moment, documentation is somewhat lacking behind. So contributions to the documentation are also welcome!

I'm currently aiming for compatibility with the latest esphome release and up to 3 months of releases before that.
Esphome is moving rather quickly and they don't have a stable api or anything to develop against... Lately a great
amount of slop has been introduced into esphome and keeping up with it is a pain already.

By the way, the zap converter tool (`tools/zap_converter.py`) is a complete mess and I kind of gave up on it... If
you like refactoring garbage python code, please do ;)

## Development environment

This project contains a `flake.nix` to make development easier and reproducible via the nix package manager, but
this is completely optional. You can enter a nix shell with `nix develop` to get access to all required tools, but
you can also install them manually.

## Code style

If you run `nix develop`, a `.pre-commit-config.yaml` is automatically generated. This way, the formatters are
always run on commits.

Alternatively, you may run `clang-format` and `ruff` manually.

## AI usage

AI is a useful tool but don't overdo it ;) A PR with 1000+ lines of senseless changes is unreviewable.
So far I have found it particularly useful for searching through the enormous connectedhomeip and esp-matter
codebases.

## Security

Use common sense. Don't commit Wi-Fi credentials, Thread datasets, etc...
