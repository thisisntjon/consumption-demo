# Frozen stateful demo fixture

This directory packages the exact helper/provider inputs used by the accepted stateful demo, including the pinned helper revision from the private website repository. The task packet uses paths relative to its own directory, so the fixture can be copied with the Consumption checkout.

Run the self-contained demo from the repository root:

```powershell
python examples/stateful_demo.py `
  --client-root examples/stateful_fixture/client `
  --engine-root . `
  --provider-root examples/stateful_fixture/provider `
  --task examples/stateful_fixture/CE-STATEFUL-001-v1/TASK.json `
  --output .tmp/stateful-frozen-run
```

The fixture is synthetic and manually annotated. It demonstrates reproducible local execution; it does not establish a physical second-machine restore, independent acceptance, semantic truth, or public release authorization.
