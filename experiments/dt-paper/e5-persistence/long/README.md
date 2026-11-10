# E5 long run: 30 days of one DT session

One session in the broker's `dt` service, kept for 30 days on one host
(radical.3), with a daily learning-endpoint loss and an hourly client
reattach.  Broker loss is out of scope: a broker restart ends the run's
epoch (`session_a_lost`, then `session_a_created` with the next epoch).

| Process | Started by | Restarted |
|---|---|---|
| broker + `dt` plugin, port 8011 | `run-long.sh`, tmux `dt-long:broker` | never |
| inference endpoint `dt_long_inf` | `run-long.sh`, tmux `dt-long:inf` | never |
| driver `dt_long.py` | `run-long.sh`, tmux `dt-long:driver` | in a loop; reattaches to session A |
| learning endpoint `dt_long_learn` | the driver | SIGKILLed every `--kill-every` s, then restarted |

- **Session A** (kept): `inf` (OffsetModel) and `lrn` (CountingSensor ->
  LinearLearner, learning on the inference endpoint).  Probed every 10 s.
- **Session B** (rebuilt per cycle): a learner twin on the learning
  endpoint.  A lost engine poisons its session (R8), so B is recreated
  after each loss.
- **Reattach**: every hour a fresh client attaches to A by sid and gets one
  answer.
- **Stats**: every 15 min, RSS, threads and fds of broker, both endpoints
  and the driver.

Events go to `$L/events/events-YYYYMMDD.jsonl` (UTC day, one JSON line per
event); `summarize_long.py` writes `summary-YYYYMMDD.json` per day and
`summary-all.json`.

## Deploy (radical.3)

```sh
L=~/dt-long && mkdir -p $L && cd $L
git clone -b paper/dtaas https://github.com/radical-cybertools/digital.twins.git
git -C digital.twins checkout <commit>            # record it; frozen for the run
DT_PYTHON=python3.12 DT_REF=<commit> digital.twins/deploy/install.sh broker $L/ve
digital.twins/experiments/dt-paper/e5-persistence/long/run-long.sh
crontab -e   # see below
```

```cron
@reboot  $HOME/dt-long/digital.twins/experiments/dt-paper/e5-persistence/long/run-long.sh
5 0 * * * $HOME/dt-long/ve/bin/python $HOME/dt-long/digital.twins/experiments/dt-paper/e5-persistence/long/summarize_long.py --events $HOME/dt-long/events --out $HOME/dt-long/summaries
```

Dry run (24 h): `DT_LONG_ARGS="--kill-every 3600" run-long.sh`, so it has
24 loss cycles instead of one.

Credentials: the default pair and token in `~/.radical/orbit` on the host.
Stop: `tmux kill-session -t dt-long` (ends the epoch, as a broker loss
does).

## Runs

| Run | Stack | Settings | Result |
|---|---|---|---|
| dry run, radical.3, 2026-11-09 13:14 to 23:58 UTC (`results/e5-long/dryrun-20261109/`) | `b24b9ab` | kill every 3600 s, probe 10 s, sensor 1 s | 3868/3868 probes per twin, 10/10 reattach, 10/10 kills detected (10.1 s), no outage; memory grew per task in every layer: inference endpoint 130 to 1100 MB, broker 134 to 356 MB |
| 30-day run, radical.3, from 2026-11-10 00:00 UTC | `044ccd9` (finished tasks released: asyncflow #128, rhapsody #134, orbit #167, DT #59) | kill every 86400 s, probe 60 s, sensor 10 s | running; ends 2026-12-10 |
