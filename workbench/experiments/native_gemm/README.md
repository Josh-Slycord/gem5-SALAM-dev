# Native GEMM study inputs

main.cpp is the two-launch template used by run_native_gemm.py. It emits fixture-bound outputs through UART and provides an explicit corruption/forced-pass control. Compilation happens only in separate evidence workspaces.

seed47.json selects the native builder through the ordinary configured pipeline.

See [the guide](../../docs/NATIVE_GEMM_CONFIGURATION.md) for commands and scope.
