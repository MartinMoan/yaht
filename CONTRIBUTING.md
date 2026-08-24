# Contributing

## Running the test suite

```bash
pip install -r requirements-dev.txt
pytest
```

The test suite exercises the h5py-facing logic in `core` (tree
navigation, column layout, threaded/cached row loading) against
generated temporary `.h5` files — it's UI-framework-agnostic and doesn't
drive the GUI itself.

## Codebase orientation

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the project
layout and the reasoning behind some of the less obvious implementation
choices (why Qt, why a frameless window, how large datasets are
streamed into the table view without loading them into memory).

## Building the packaged app

See [`packaging/README.md`](packaging/README.md).
