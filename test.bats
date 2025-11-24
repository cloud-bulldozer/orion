#!/usr/bin/env bats
# vi: ft=bash
# shellcheck disable=SC2086,SC2030,SC2031,SC2164


run_cmd(){
  echo "$@"
  set +e
  "${@}"
  EXIT_CODE=$?
  set -e

  if [ $EXIT_CODE -eq 2 ]; then
    echo "Exit code 2 encountered, regression detected, treating as success"
    return 0
  elif [ $EXIT_CODE -eq 3 ]; then
    echo "Exit code 3 encountered, not enough data, treating as success"
    return 0
  else
    return $EXIT_CODE
  fi
}

setup() {
  ES_SERVER="$QE_ES_SERVER"
  METADATA_INDEX="perf_scale_ci*"
  BENCHMARK_INDEX="ripsaw-kube-burner*"
  KRKN_BENCHMARK_INDEX=krkn-metrics*
  KRKEN_METADATA_INDEX=krkn-telemetry*
  LATEST_VERSION=$(curl -s -X POST "$ES_SERVER/perf_scale_ci*/_search" \
  -H "Content-Type: application/json" \
  -d '{
    "size": 0,
    "query": {
      "bool": {
        "must": [
          {
            "range": {
              "timestamp": {
                "gte": "now-1M/M",
                "lt": "now/M"
              }
            }
          }
        ],
        "must_not": [
          { "wildcard": { "releaseStream.keyword": "*nightly*" } },
          { "wildcard": { "releaseStream.keyword": "*rc*" } },
          { "wildcard": { "releaseStream.keyword": "*ci*" } },
          { "wildcard": { "releaseStream.keyword": "*ec*" } },
          { "wildcard": { "releaseStream.keyword": "*okd*" } }
        ]
      }
    },
    "aggs": {
      "distinct_versions": {
        "terms": {
          "field": "releaseStream.keyword",
          "order": { "_key": "desc" }
        }
      }
    }
  }' | jq -r '.aggregations.distinct_versions.buckets[0].key')
  export VERSION=$(echo "$LATEST_VERSION" | cut -d. -f1,2)

  CHAOS_LATEST_VERSION=$(curl -s -X POST "$ES_SERVER/krkn-telemetry*/_search" \
  -H "Content-Type: application/json" \
  -d '{
    "size": 0,
    "query": {
      "bool": {
        "must": [
          {
            "range": {
              "timestamp": {
                "gte": "now-1M/M",
                "lt": "now/M"
              }
            }
          }
        ],
        "filter": [
          {
            "match_phrase": {
              "scenarios.scenario_type.keyword": "node_scenarios"
            }
          }
        ]
      }
    },
    "aggs": {
      "distinct_versions": {
        "terms": {
          "field": "cluster_version.keyword",
          "order": { "_key": "desc" }
        }
      }
    }
  }' | jq -r '.aggregations.distinct_versions.buckets[0].key')
  export chaos_version=$(echo "$CHAOS_LATEST_VERSION" | cut -d'.' -f1,2)
  echo "chaos version $chaos_version"

  OLS_LATEST_VERSION=$(curl -s -X POST "$ES_SERVER/perf_scale_ci*/_search" \
  -H "Content-Type: application/json" \
  -d '{
    "size": 0,
    "query": {
      "bool": {
        "must": [
          {
            "range": {
              "timestamp": {
                "gte": "now-1M/M",
                "lt": "now/M"
              }
            }
          },
          {
          "match_phrase": {
            "benchmark.keyword": "ols-load-generator"
          }
        }
        ]
      }
    },
    "aggs": {
      "distinct_versions": {
        "terms": {
          "field": "ocpVersion.keyword",
          "order": { "_key": "desc" }
        }
      }
    }
  }' | jq -r '.aggregations.distinct_versions.buckets[0].key')
  export ols_version=$(echo "$OLS_LATEST_VERSION" | cut -d'.' -f1,2)

  QUAY_LATEST_VERSION=$(curl -s -X POST "$QUAY_QE_ES_SERVER/perf_scale_ci*/_search" \
  -H "Content-Type: application/json" \
  -d '{
    "size": 0,
    "query": {
      "range": {
        "timestamp": {
          "gte": "now-3M/M",
          "lt": "now"
        }
      }
    },
    "aggs": {
      "latest_version": {
        "terms": {
          "field": "quayVersion.keyword",
          "size": 1,
          "order": { "_key": "desc" },
          "exclude": "quayio-stage.*"
        }
      }
    }
  }' | jq -r '.aggregations.latest_version.buckets[0].key')
  export quay_version=$(echo "$QUAY_LATEST_VERSION" | cut -d'.' -f1,2)
}

@test "orion label small scale cluster density with hunter-analyze" {
  run_cmd orion --config "examples/label-small-scale-cluster-density.yaml" --lookback 45d --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion label small scale cluster density with hunter-analyze and using env vars for ES" {
  export ES_SERVER=${ES_SERVER} es_metadata_index=${METADATA_INDEX} es_benchmark_index=${BENCHMARK_INDEX}
  run_cmd orion --config "examples/label-small-scale-cluster-density.yaml" --lookback 45d --hunter-analyze --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion payload scale" {
  run_cmd orion --config "examples/payload-scale.yaml" --lookback 45d --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion payload scale without lookback period" {
  run_cmd orion --config "examples/payload-scale.yaml" --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion readout control plane cdv2 with text output " {
  run_cmd orion --config "examples/label-small-scale-cluster-density.yaml" --hunter-analyze --output-format text --save-output-path=output.txt --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX}
}

@test "orion label small control plane cdv2 with json output " {
  run_cmd orion --config "examples/label-small-scale-cluster-density.yaml" --hunter-analyze --output-format json --save-output-path=output.json --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX}
}

@test "orion readout control plane node-density with json output and match all iterations " {
  run_cmd orion --config "examples/small-rosa-control-plane-node-density.yaml" --hunter-analyze --output-format json --save-output-path=output.json --node-count True --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX}
}

@test "orion readout netperf tcp with junit output" {
  run_cmd orion --config "examples/readout-netperf-tcp.yaml" --output-format junit --hunter-analyze --save-output-path=output.xml --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=k8s-netperf --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion virt-density" {
  run_cmd orion --config examples/metal-perfscale-cpt-virt-density.yaml --lookback 45d --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion small scale cluster density with anomaly detection" {
  run_cmd orion --config "examples/small-scale-cluster-density.yaml" --lookback 45d --anomaly-detection --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion small scale node density cni anomaly detection with a window" {
  run_cmd orion --config "examples/small-scale-node-density-cni.yaml" --anomaly-detection --anomaly-window 3 --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion trt external payload cluster density anomaly detection with a minimum percentage" {
  run_cmd orion --config "examples/trt-external-payload-cluster-density.yaml" --anomaly-detection --anomaly-window 3 --min-anomaly-percent 5 --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion trt external payload crd scale with default anomaly detection" {
  run_cmd orion --config "examples/trt-external-payload-crd-scale.yaml" --anomaly-detection --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion trt external payload node density" {
  run_cmd orion --config "examples/trt-external-payload-node-density.yaml" --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion trt external payload node density json" {
  run_cmd orion --config "examples/trt-external-payload-node-density.yaml" --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}' --output-format json
}

@test "orion trt external payload node density junit" {
  run_cmd orion --config "examples/trt-external-payload-node-density.yaml" --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}' --output-format junit
}

@test "orion trt external payload node density json with lookback" {
  run_cmd orion --config "examples/trt-external-payload-node-density.yaml" --hunter-analyze --lookback 15d --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}' --output-format json
}

@test "orion trt external payload node density junit with lookback" {
  run_cmd orion --config "examples/trt-external-payload-node-density.yaml" --hunter-analyze --lookback 15d --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}' --output-format junit
}

@test "orion trt external payload cluster density" {
  run_cmd orion --config "examples/trt-payload-cluster-density.yaml" --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion trt external payload cluster density for pull" {
  run_cmd orion --config "examples/trt-payload-cluster-density.yaml" --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'", "jobType": "pull", "pullNumber": "70897"}'
}

@test "orion trt external payload cluster density for periodic from a pull" {
  run_cmd orion --config "examples/trt-payload-cluster-density.yaml" --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'", "jobType": "periodic", "pullNumber": "70897"}'
}

@test "orion chaos tests " {
  before_version=$version
  scenario_type="pvc_scenarios" cloud_infrastructure="aws" cloud_type="self-managed" total_node_count="9" node_instance_type="m6a.xlarge" network_plugins="OVNKubernetes" scenario_file="*pvc_scenario.yaml" run_cmd orion --config "examples/chaos_tests.yaml" --lookback 45d --es-server=${ES_SERVER} --metadata-index=${KRKEN_METADATA_INDEX} --benchmark-index=${KRKN_BENCHMARK_INDEX} --input-vars='{"version": "'${chaos_version}'"}' --output-format text
  VERSION=$before_version
}

@test "orion node scenarios " {
  before_version=$version
  VERSION=$chaos_version
  scenario_type="node_scenarios" cloud_infrastructure="AWS" cloud_type="self-managed" total_node_count="9" node_instance_type="*xlarge*" network_plugins="OVNKubernetes" scenario_file="*node_scenario.yaml" run_cmd orion --config "examples/node_scenarios.yaml" --lookback 45d --es-server=${ES_SERVER} --metadata-index=${KRKEN_METADATA_INDEX} --benchmark-index=${KRKN_BENCHMARK_INDEX}
  VERSION=$before_version
}

@test "orion pod disruption scenarios " {
  before_version=$version
  VERSION=$chaos_version
  pod_namespace="openshift-etcd" scenario_type="pod_disruption_scenarios" cloud_infrastructure="AWS" cloud_type="self-managed" total_node_count="9" node_instance_type="*xlarge*" network_plugins="OVNKubernetes" scenario_file="*pod_scenario.yaml" run_cmd orion --config "examples/pod_disruption_scenarios.yaml" --lookback 45d --es-server=${ES_SERVER} --metadata-index=${KRKEN_METADATA_INDEX} --benchmark-index=${KRKN_BENCHMARK_INDEX} --hunter-analyze
  VERSION=$before_version
}

@test "orion ols configuration test " {
  before_version=$version
  VERSION=$ols_version
  export ols_test_workers=10
  es_metadata_index="perf_scale_ci*" es_benchmark_index="ols-load-test-results*" run_cmd orion --config "examples/ols-load-generator.yaml" --hunter-analyze --ack ack/4.15_ols-load-generator-10w_ack.yaml --es-server=${ES_SERVER}
  VERSION=$before_version
}

@test "orion with netobserv configs " {
  BENCHMARK_INDEX="prod-netobserv-datapoints*"
  curl -s https://raw.githubusercontent.com/openshift-eng/ocp-qe-perfscale-ci/refs/heads/netobserv-perf-tests/scripts/queries/netobserv-orion-node-density-heavy.yaml -w %{http_code} -o /tmp/netobserv-node-density-heavy-ospst.yaml
  run_cmd orion --config "/tmp/netobserv-node-density-heavy-ospst.yaml" --lookback 45d --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"workers": 25}'
}

@test "orion with quay config " {
  export quay_image_push_pull_index="quay-push-pull*"
  export quay_load_test_index="quay-vegeta-results*"
  export es_metadata_index=${METADATA_INDEX}
  run_cmd orion --node-count false --config "examples/quay-load-test-stable.yaml" --hunter-analyze --es-server=${QUAY_QE_ES_SERVER} --output-format junit --save-output-path=junit.xml --collapse --input-vars='{"quay_version": "'${quay_version}'", "ocp_version": "4.18"}'
}

@test "orion with quay stage config " {
  export quay_image_push_pull_index="quay-push-pull*"
  export es_metadata_index=${METADATA_INDEX}
  run_cmd orion --node-count false --config "examples/quay-load-test-stable-stage.yaml" --hunter-analyze --es-server=${QUAY_QE_ES_SERVER} --output-format junit --save-output-path=junit.xml --collapse --input-vars='{"quay_version": "quayio-stage", "ocp_version": "4.18"}'
}

@test "orion version check" {
  set +e
  version=$(orion --version)
  echo $version
  expected_tag=$(git tag -l | sort -V | tail -1)
  expected_tag=${expected_tag#v}
  if [[ -z $expected_tag ]]; then
    expected_tag=0.0
  fi

  expected_version="orion ${expected_tag}"

  last_commit=$(git rev-parse --short=7 HEAD)
  describe=$(git describe --tags --dirty --always)

  if [[ "$describe" == *"$last_commit"* ]]; then
    echo "Is ahead of Tag adding '.post1.dev'"
    expected_version+=".post1.dev"
  fi

  if [[ "$describe" == *"dirty"* ]]; then
    if [[ ! "$version" == *"+dirty"* ]]; then
      echo "Failed checking for dirty append"
      exit 1
    fi
  fi

  echo $expected_version

  if [[ ! "$version" == *"$expected_version"* ]]; then
    exit 1
  fi
  set -e
}

@test "orion with regression should contain inline changepoint" {
  set +e

  orion --node-count true --lookback 20d --hunter-analyze --config examples/trt-external-payload-node-density.yaml --metadata-index=${METADATA_INDEX} --es-server=${QE_ES_SERVER} --since 2025-11-24 --input-vars='{"version": "4.21"}' > ./outputs/results.txt
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  # Check if the percentage string exists in the output file
  if ! grep -q "+12.1%" ./outputs/results.txt; then
    echo "Expected string '+12.1%' not found in results.txt"
    exit 1
  fi

  # Check if the Previous Version string exists in the output file
  if ! grep -q "Previous Version:    4.21.0-0.nightly-2025-11-11-181704" ./outputs/results.txt; then
    echo "Expected string 'Previous Version:    4.21.0-0.nightly-2025-11-11-181704' not found in results.txt"
    exit 1
  fi

  # Check if the Bad Version string exists in the output file
  if ! grep -q "Bad Version:         4.21.0-0.nightly-2025-11-12-020146" ./outputs/results.txt; then
    echo "Expected string 'Bad Version:         4.21.0-0.nightly-2025-11-12-020146' not found in results.txt"
    exit 1
  fi

  set -e
}

@test "orion with regression should contain inline changepoint json" {
  set +e

  orion --node-count true --lookback 20d --hunter-analyze --config examples/trt-external-payload-node-density.yaml --metadata-index=${METADATA_INDEX} --es-server=${QE_ES_SERVER} --since 2025-11-24 --input-vars='{"version": "4.21"}' --output-format json > ./outputs/results.json
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  bad_version=$(jq -r '.[] | select(.is_changepoint == true) | .ocpVersion' ./outputs/results.json)

  if [ "$bad_version" != "4.21.0-0.nightly-2025-11-12-020146" ]; then
    echo "Version did not match. Expected '4.21.0-0.nightly-2025-11-12-020146', got '$bad_version'"
    exit 1
  fi
  set -e
}

@test "orion with regression should contain inline changepoint junit" {
  set +e

  orion --node-count true --lookback 20d --hunter-analyze --config examples/trt-external-payload-node-density.yaml --metadata-index=${METADATA_INDEX} --es-server=${QE_ES_SERVER} --since 2025-11-24 --input-vars='{"version": "4.21"}' --output-format junit > ./outputs/results.xml
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  failure=$(echo 'failures="1"')
  # Check if the failures string exists in the output file
  if ! grep -q $failure ./outputs/results.xml; then
    echo "Expected string '$failure' not found in results.xml"
    cat ./outputs/results.xml
    exit 1
  fi

  changepoint=$(echo '12.0871 | -- changepoint')
  # Check if the changepoint string exists in the output file
  if ! grep -q $changepoint ./outputs/results.xml; then
    echo "Expected string '$changepoint' not found in results.xml"
    cat ./outputs/results.xml
    exit 1
  fi

  set -e
}