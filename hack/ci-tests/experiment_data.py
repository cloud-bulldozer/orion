#!/usr/bin/env python3
"""
Synthetic experiment dataset for local integration testing.

15 test runs (01-12 .. 01-26, one per day) carrying a single metric
(catalogd_cpu_usage_cores_experiment) shaped as a slow ramp:

  Runs  1-5  (01-12 .. 01-16): flat at 100.0 (no change)
  Runs  6-15 (01-17 .. 01-26): constant steady rise of +1% per run
                               (101.0, 102.0, ... 110.0)

Only one metric document is generated per run, so each run yields exactly
one aggregated data point and the series Orion analyzes has 15 points.

The value schedule is defined explicitly (no float accumulation) so the
generated data is deterministic and the +1%/run ramp is exact.
"""

BASE_VALUE = 100.0
METRIC_NAME = "catalogd_cpu_usage_cores_experiment"

# Runs 6-15: constant +1% rise per run (101.0 .. 110.0). Ten rising runs.
EXP_RISE_VALUES = [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0]

# (uuid, ocpVersion, executionDate) — one run per day, oldest first
EXP_RUNS = [
    ("ci-exp-01", "4.20.0-0.nightly-2026-01-11-195655", "2026-01-12T10:20:30Z"),
    ("ci-exp-02", "4.20.0-0.nightly-2026-01-12-195655", "2026-01-13T10:20:30Z"),
    ("ci-exp-03", "4.20.0-0.nightly-2026-01-13-195655", "2026-01-14T10:20:30Z"),
    ("ci-exp-04", "4.20.0-0.nightly-2026-01-14-195655", "2026-01-15T10:20:30Z"),
    ("ci-exp-05", "4.20.0-0.nightly-2026-01-15-195655", "2026-01-16T10:20:30Z"),
    ("ci-exp-06", "4.20.0-0.nightly-2026-01-16-195655", "2026-01-17T10:20:30Z"),
    ("ci-exp-07", "4.20.0-0.nightly-2026-01-17-195655", "2026-01-18T10:20:30Z"),
    ("ci-exp-08", "4.20.0-0.nightly-2026-01-18-195655", "2026-01-19T10:20:30Z"),
    ("ci-exp-09", "4.20.0-0.nightly-2026-01-19-195655", "2026-01-20T10:20:30Z"),
    ("ci-exp-10", "4.20.0-0.nightly-2026-01-20-195655", "2026-01-21T10:20:30Z"),
    ("ci-exp-11", "4.20.0-0.nightly-2026-01-21-195655", "2026-01-22T10:20:30Z"),
    ("ci-exp-12", "4.20.0-0.nightly-2026-01-22-195655", "2026-01-23T10:20:30Z"),
    ("ci-exp-13", "4.20.0-0.nightly-2026-01-23-195655", "2026-01-24T10:20:30Z"),
    ("ci-exp-14", "4.20.0-0.nightly-2026-01-24-195655", "2026-01-25T10:20:30Z"),
    ("ci-exp-15", "4.20.0-0.nightly-2026-01-25-195655", "2026-01-26T10:20:30Z"),
]

# Per-run metric value (run 1 is oldest). Runs 1-5 flat, runs 6-15 rising.
def exp_run_values():
    """Return the 15 metric values, oldest run first."""
    values = [BASE_VALUE] * 5
    values.extend(EXP_RISE_VALUES[: len(EXP_RUNS) - 5])
    assert len(values) == len(EXP_RUNS)
    return values


def _exp_metadata_entry(uuid, ocp_version, execution_date):
    return {
        "ciSystem": "PROW",
        "uuid": uuid,
        "releaseStream": "4.20.0-0.nightly",
        "platform": "GCP",
        "clusterType": "self-managed",
        "benchmark": "olm",
        "masterNodesCount": 3,
        "workerNodesCount": 3,
        "infraNodesCount": 3,
        "masterNodesType": "e2-custom-6-16384",
        "workerNodesType": "e2-custom-6-16384",
        "infraNodesType": "n1-standard-16",
        "totalNodesCount": 9,
        "clusterName": "ci-exp-" + uuid[-2:],
        "ocpVersion": ocp_version,
        "stream": "ocp",
        "osImage": "Red Hat Enterprise Linux CoreOS 9.6.20260117-0 (Plow)",
        "ocpVirt": "false",
        "ocpVirtVersion": "",
        "ocpVirtTuningPolicy": "",
        "networkType": "OVNKubernetes",
        "ovnVersion": "25.03.2",
        "buildTag": "0",
        "jobStatus": "success",
        "jobType": "periodic",
        "buildUrl": "https://prow.ci/" + uuid,
        "upstreamJob": "periodic-ci-exp-olm-benchmark-test",
        "upstreamJobBuild": uuid,
        "executionDate": execution_date,
        "jobDuration": "1609",
        "startDate": execution_date,
        "endDate": execution_date,
        "timestamp": execution_date,
        "ipsec": "false",
        "ipsecMode": "Disabled",
        "fips": "false",
        "encrypted": "false",
        "encryptionType": "",
        "publish": "External",
        "computeArch": "amd64",
        "controlPlaneArch": "amd64",
        "pullNumber": "0",
        "organization": "openshift-eng",
        "repository": "ocp-qe-perfscale-ci",
    }


def exp_metadata_docs():
    """Return the 15 experiment metadata documents, oldest run first."""
    return [_exp_metadata_entry(uuid, ver, date)
            for uuid, ver, date in EXP_RUNS]


def exp_metric_docs():
    """Return the 15 experiment metric documents, oldest run first.

    One document per run (the run's execution date as timestamp) so the
    aggregated series Orion analyzes has exactly 15 data points.
    """
    docs = []
    for (uuid, ocp_version, execution_date), value in zip(EXP_RUNS, exp_run_values()):
        docs.append({
            "timestamp": execution_date,
            "value": value,
            "uuid": uuid,
            "query": 'sum(rate(container_cpu_usage_seconds_total{namespace="openshift-catalogd"}[1m]))',
            "metricName": METRIC_NAME,
            "jobName": "create-clusterextensions",
            "metadata": {
                "ocpMajorVersion": "4.20",
                "ocpVersion": ocp_version,
            },
        })
    return docs
