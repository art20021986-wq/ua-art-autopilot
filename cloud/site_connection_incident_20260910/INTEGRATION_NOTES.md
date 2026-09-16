# UA ART connection monitor — prepared, not activated

Baseline: `.github/workflows/uaart_monitor.yml` at main
`8866d83e52197703a2f148ec882d560090ed62c9`. The exact original is
`baseline_uaart_monitor.yml` in this directory.

The current workflow runs at `17 */6 * * *` and fetches two direct `www` pages.
It exits before writing evidence if either public request fails; its upload step
also lacks `if: always()`. Neither root URL is checked. This is a monitoring gap,
not evidence that the gap causes browser connection failures.

## Prepared files

- `uaart_connection_monitor.py`: Python standard library only. Four concurrent
  public GET probes: apex root, www root, homepage and `/video/katalog.html`.
  Root URLs must resolve to `https://www.uaart.com.ua/video/index.html`.
- `test_uaart_connection_monitor.py`: eighteen functional tests with stubbed
  transport and no external network requests.

TLS verification is enabled; HTTP downgrades, other hosts and unexpected final
paths fail. Each probe has a unique query token and cache-control headers.
Responses are restricted to HTML, 500 bytes to 1 MiB, with an HTML document
element and `UA ART` branding in the title. Live confirmed titles:
`UA ART COMPANY — автомобили под ключ в Киеве` and
`Каталог автомобилей — UA ART COMPANY`. Healthy response SHA-256 is retained. Compare actual page sizes before
integration because the previous upper bound was 10 MiB.

Each attempt checks all four URLs, in parallel. A subprocess enforces the
20-second wall-clock limit, including DNS, TLS, redirects and reading. After any
failed attempt, retry the complete group after 15 seconds; stop after three
attempts. Normal maximum network/retry duration is about 90 seconds plus process
and artifact overhead. Workers inherit Python isolated mode (`-I`).

Evidence is written at startup, after every completed round and at completion;
normal request failures cannot suppress the JSON. Writes replace the file
atomically. Abrupt termination can leave the last completed evidence with
`running` status, rather than a fabricated success. Disk or checkout failure
still requires the workflow's own failure reporting.

Exit codes: `0` healthy or recovered transient; `2` persistent failure;
`3` monitor/internal error; `130` interrupted. A recovered transient has its own
JSON status and retains the failed round. It must be shown as a warning/history
event, never relabeled as an uninterrupted healthy run.

## Integration steps — do not bypass runtime policy

1. Add script and tests on an isolated review branch. Run offline tests with:
   `python3 -m unittest discover -s incident_monitor -p 'test_*.py' -v`.
2. Preserve the existing control-plane file checks and `contents: read`, pinned
   actions, `persist-credentials: false`, main-ref guard and no production secrets.
   The new script checks transport only; it does not replace those file checks.
3. Once approved through the legitimate workflow registration path, invoke the
   script with `python3 -I incident_monitor/uaart_connection_monitor.py
   --evidence /tmp/uaart-monitor.json`. Make artifact upload use `if: always()`
   and `if-no-files-found: error`. Surface transient recovery in the run summary.
4. The runtime currently requires an exact set of nine pinned workflows and
   activation hashes. A changed/added workflow needs legitimate new registration
   and reviewed hash/activation updates. Do not loosen the gate, edit its required
   set opportunistically, or dispatch an unregistered monitor as a workaround.
5. Test actual endpoints and confirm root redirects before enabling recurrence.
   No workflow, schedule, activation hash, server file or external state was
   changed as part of this preparation.

## Limits that matter for this incident

This module does not reload the application, deploy code, change DNS, send
notifications or create external schedules. It is not an automatic repair mechanism.
It validates transport, expected destinations and branded titles, not full
business content. A branded error page returning 200 can still pass.

A pass from a GitHub runner cannot prove access from an iPhone, a Vietnamese
mobile carrier or the TikTok in-app browser. Live diagnosis must also examine
DNS/TLS and the user's network path. More frequent GitHub scheduled checks alone
cannot guarantee real-time detection or prevent an outage; schedules can be
delayed. Automatic server reload is inappropriate for an unconfirmed connection
failure because it may not fix DNS/TLS/routing and can itself interrupt service.

## Optional PythonAnywhere Always-on mode

Default behavior remains one-shot. Python 3.10-compatible Linux/POSIX watch mode:

```bash
python3.10 -I /home/Carix/uaart_connection_monitor.py --watch --interval 300 --evidence /home/Carix/uaart-monitor/latest.json
```

Only start this reviewed command through the already authorized PythonAnywhere
Always-on interface. It is an independent read-only process; it does not edit or
activate the existing runtime workflows, production app or control-plane gates.

A nonblocking `fcntl` exclusive lock on `.uaart-monitor.lock` in the evidence
directory rejects duplicate watchers with exit code `4`. The lock is held for
the session and is released when the process exits. All watchers for this site
must use the same evidence directory so they share the lock.

Each cycle updates the same `latest.json`. Any nonhealthy or recovered-transient
result also replaces `last_incident.json`; subsequent healthy cycles preserve
that incident. These are fixed files, without accumulating JSON history or
application log files. Watch stdout contains one timestamp/status line per
cycle, flushed immediately; PythonAnywhere owns any platform log retention.
The loop waits 300 seconds **after completion** of each cycle, so a failed
90-second check group is followed by the same 300-second wait.

The hidden subprocess entry point also enforces the fixed four URL/expected-path
pairs. There is no arbitrary-host option, reload, token/API call or notification.
Offline tests additionally verify duplicate-lock rejection, incident retention
after a healthy cycle, a single stubbed watch cycle and bogus HTML rejection.
