# Upper bounds

No-op task rates of the tools underneath the DT layer.  The DT numbers
in E1 and E2 are read against these.

| Script      | Measures                                                        |
|-------------|-----------------------------------------------------------------|
| `tasks.py`  | asyncio task create/destroy rate, 100k to 1M tasks              |
| `af.py`     | AsyncFlow no-op function tasks and blocks vs plain coroutines and plain calls, 1k to 10k each, on a 128-worker process pool (Dragon and no-op backends commented out) |
| `uvtest.py` | the same four rows on the uvloop event loop, default process pool |

```sh
python experiments/dt-paper/bounds/tasks.py
```
