# Mini harness

A three-file example used to exercise `pohe-agent`. It contains a bounded agent
loop, deferred tool discovery, and a permission prefix check. The workflow is
real enough to retrieve a few pattern cues, and small enough to read in one
sitting.

```bash
pohe-agent scan examples/mini_harness --markdown /tmp/mini-report.md
pohe-agent match examples/mini_harness --pattern P01,P09,P23
```
