| harness | layout | c | N | repeats | bursts 2-5 req/s | x N=1 | seq p50 ms | placement ok | errors |
|---|---|---|---|---|---|---|---|---|---|
| dt | spread | 16 | 1 | 5 | 20.7 (20.3-21.0) | 1.00 | 56.9 | 5/5 | 0 |
| dt | spread | 16 | 4 | 5 | 77.9 (77.6-78.2) | 3.76 | 57.5 | 5/5 | 0 |
| dt | spread | 32 | 1 | 5 | 21.6 (20.6-22.3) | 1.00 | 56.9 | 5/5 | 0 |
| dt | spread | 32 | 4 | 5 | 80.1 (79.4-81.4) | 3.71 | 57.4 | 5/5 | 0 |
| xgf | spread | 16 | 1 | 5 | 25.0 (23.1-25.7) | 1.00 | 55.2 | 5/5 | 0 |
| xgf | spread | 16 | 4 | 5 | 80.0 (79.8-80.5) | 3.20 | 56.1 | 5/5 | 0 |
| xgf | spread | 32 | 1 | 5 | 51.3 (47.9-56.7) | 1.00 | 55.2 | 5/5 | 0 |
| xgf | spread | 32 | 4 | 5 | 88.2 (87.0-88.7) | 1.72 | 56.3 | 5/5 | 0 |

Code per site:

- dt spread N=4: `{"engine_config_entry": {"site_3": {"endpoint_name": "e3_s3", "backends": ["concurrent"]}}, "agent_sites_entry": "site_3", "lines": 2}`
- dt spread N=4: `{"engine_config_entry": {"site_3": {"endpoint_name": "e3_s3", "backends": ["concurrent"]}}, "agent_sites_entry": "site_3", "lines": 2}`
- xgf spread N=4: `{"SITES_entry": "e3_s3", "lines": 1}`
- xgf spread N=4: `{"SITES_entry": "e3_s3", "lines": 1}`
- xgf: wiring_lines 65
