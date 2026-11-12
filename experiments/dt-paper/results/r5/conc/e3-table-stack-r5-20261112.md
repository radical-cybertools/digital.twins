| harness | layout | c | N | repeats | bursts 2-5 req/s | x N=1 | seq p50 ms | placement ok | errors |
|---|---|---|---|---|---|---|---|---|---|
| dt | spread | 32 | 1 | 3 | 50.3 (49.7-51.9) | 1.00 | 56.5 | 3/3 | 0 |
| dt | spread | 32 | 4 | 3 | 129.1 (128.2-130.5) | 2.57 | 57.1 | 3/3 | 0 |
| xgf | spread | 32 | 1 | 3 | 54.9 (53.7-56.6) | 1.00 | 55.2 | 3/3 | 0 |
| xgf | spread | 32 | 4 | 3 | 138.0 (136.9-140.0) | 2.51 | 56.1 | 3/3 | 0 |

Code per site:

- dt spread N=4: `{"engine_config_entry": {"site_3": {"endpoint_name": "e3_s3", "backends": ["concurrent"]}}, "agent_sites_entry": "site_3", "lines": 2}`
- xgf spread N=4: `{"SITES_entry": "e3_s3", "lines": 1}`
- xgf: wiring_lines 65
