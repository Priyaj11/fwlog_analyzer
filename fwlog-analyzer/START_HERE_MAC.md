# Start Here (Mac) — read this first

You unzipped this folder. Now let's run it. Follow these exactly.

## Step 0 — open Terminal in this folder

1. Open the **Terminal** app (press Cmd+Space, type "Terminal", hit Enter).
2. Type `cd ` (the letters c, d, then a SPACE) but do NOT press Enter yet.
3. Drag the **fwlog-analyzer** folder from Finder onto the Terminal window. It
   pastes the location for you.
4. Now press Enter.

Your prompt should now end with `fwlog-analyzer %`. That means you're inside
the right folder. (You need to be here for every command below.)

## Step 1 — check Python exists

On a Mac, Python is called `python3` (with the 3). Run:

```
python3 --version
```

- See `Python 3.x.x`? Great, continue.
- See `command not found`? Install Python from https://www.python.org/downloads
  (big yellow Download button → open the file → click through). Close Terminal,
  reopen it, redo Step 0, then try again.

## Step 2 — make a fake device log

```
python3 -m fwlog generate device.log --duration 8 --seed 3
```

You should see `wrote device.log: ...` and a line of "injected ground truth".
(This creates a pretend embedded-computer log with some hidden problems in it.)

## Step 3 — analyze it

```
python3 -m fwlog analyze device.log
```

This prints the report: each task's timing, whether the system is overloaded,
and the faults it found (including a red-flag WATCHDOG reset).

## Step 4 — make the charts too (optional)

The charts need one extra library. Install it once:

```
python3 -m pip install matplotlib
```

Then:

```
python3 -m fwlog report device.log --outdir out
```

Open the new **out** folder — you'll see `timeline.png`, `jitter.png`,
`anomalies.png`, and `report.txt`.

## Step 5 — prove it all works (nice for a class report)

Install the test tool once, then run the tests:

```
python3 -m pip install pytest
python3 -m pytest
```

You should see **21 passed**. Screenshot that green line — it's proof your
project works.

---

### If you see "No module named fwlog"

You're not inside the right folder. Redo **Step 0** (the `cd` + drag trick) so
your prompt ends with `fwlog-analyzer %`, then try the command again.

### What is this project?

A tool that reads messy logs from tiny embedded computers (like the chip in a
drone) and automatically finds timing problems and crashes. Plain-English
overview is in `README.md`; the deeper "why/how" with the math is in
`docs/TECHNICAL_WRITEUP.md`.
