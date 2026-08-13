import random

from fwlog.anomaly import rolling_zscore, rolling_mad, detect


def test_mad_flags_single_spike():
    series = [1.0] * 60
    series[45] = 20.0
    anoms = rolling_mad(series, window=20, thresh=3.5)
    assert any(a.index == 45 for a in anoms)


def test_mad_robust_to_masking():
    # two adjacent spikes: MAD (robust) should still flag both;
    # z-score can be "masked" because the spikes inflate the running std.
    series = [1.0] * 60
    series[40] = 15.0
    series[41] = 15.0
    mad = rolling_mad(series, window=20)
    idxs = {a.index for a in mad}
    assert 40 in idxs and 41 in idxs


def test_no_false_positives_on_clean_signal():
    rng = random.Random(0)
    series = [rng.gauss(10.0, 0.01) for _ in range(300)]
    anoms = rolling_mad(series, window=30, thresh=3.5)
    # allow a tiny number of statistical false positives, but not many
    assert len(anoms) <= 5


def test_zscore_runs_and_detects():
    series = [5.0] * 50
    series[30] = 50.0
    anoms = rolling_zscore(series, window=15, thresh=3.0)
    assert any(a.index == 30 for a in anoms)


def test_detect_dispatch_and_bad_method():
    assert detect([1, 1, 1, 9, 1, 1], method="mad", window=3) is not None
    try:
        detect([1, 2, 3], method="bogus")
        assert False, "should have raised"
    except ValueError:
        pass
