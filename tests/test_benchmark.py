from ride_matcher.benchmark import benchmark


def test_snapshot_benchmark_measures_eta_not_live_wait_time():
    report = benchmark()
    assert report['matched'] == 19 and report['no_match'] == 1
    assert report['nearest_available_total_minutes'] == 113
    assert report['matcher_total_minutes'] == 60
    assert report['aggregate_eta_reduction_percent'] == 46.9
