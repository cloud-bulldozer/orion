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
    echo "Exit code 3 encountered, not enough data"
    return 0
  else
    return $EXIT_CODE
  fi
}

setup() {
  # Make a note of daemon PID
  ES_SERVER="$QE_ES_SERVER"
  METADATA_INDEX="perf_scale_ci*"
  BENCHMARK_INDEX="ripsaw-kube-burner*"
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
          { "wildcard": { "releaseStream.keyword": "*ec*" } }
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
  VERSION=$(echo "$LATEST_VERSION" | cut -d. -f1,2)
}

@test "orion cmd label small scale cluster density with hunter-analyze" {
  run_cmd orion cmd --config "examples/label-small-scale-cluster-density.yaml" --lookback 5d --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion cmd payload scale" {
  run_cmd orion cmd --config "examples/payload-scale.yaml" --lookback 5d --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion cmd payload scale without lookback period" {
  run_cmd orion cmd --config "examples/payload-scale.yaml" --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion cmd readout control plane cdv2 with text output" {
  run_cmd orion cmd --config "examples/readout-control-plane-cdv2.yaml" --hunter-analyze --output-format text --save-output-path=output.txt --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion cmd readout control plane node-density with json output" {
  run_cmd orion cmd --config "examples/readout-control-plane-node-density.yaml" --hunter-analyze --output-format json --save-output-path=output.json --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion cmd readout control plane node-density with json output and match all iterations" {
  run_cmd orion cmd --config "examples/readout-control-plane-node-density.yaml" --hunter-analyze --output-format json --save-output-path=output.json --node-count True --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion cmd readout netperf tcp with junit output" {
  run_cmd orion cmd --config "examples/readout-netperf-tcp.yaml" --output-format junit --hunter-analyze --save-output-path=output.xml --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=k8s-netperf --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion cmd virt-density" {
  run_cmd orion cmd --config examples/metal-perfscale-cpt-virt-density.yaml --lookback 15d --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion cmd small scale cluster density with anomaly detection" {
  run_cmd orion cmd --config "examples/small-scale-cluster-density.yaml" --lookback 5d --anomaly-detection --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion cmd small scale node density cni anomaly detection with a window" {
  run_cmd orion cmd --config "examples/small-scale-node-density-cni.yaml" --anomaly-detection --anomaly-window 3 --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion cmd trt external payload cluster density anomaly detection with a minimum percentage" {
  run_cmd orion cmd --config "examples/trt-external-payload-cluster-density.yaml" --anomaly-detection --anomaly-window 3 --min-anomaly-percent 5 --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion cmd trt external payload crd scale with default anomaly detection" {
  run_cmd orion cmd --config "examples/trt-external-payload-crd-scale.yaml" --anomaly-detection --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion cmd trt external payload node density" {
  run_cmd orion cmd --config "examples/trt-external-payload-node-density.yaml" --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion cmd trt external payload cluster density" {
  run_cmd orion cmd --config "examples/trt-payload-cluster-density.yaml" --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion cmd chaos pod recovery" {
  run_cmd orion cmd --config "examples/chaos_results.yaml" --lookback 10d --es-server=${ES_SERVER} --metadata-index=krkn-telemetry* --benchmark-index=krkn-metrics* --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion cmd ols configuration test" {
  run_cmd orion cmd --config "examples/ols-load-generator.yaml" --hunter-analyze --ack ack/4.15_ols-load-generator-10w_ack.yaml --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=ols-load-test-results* --input-vars='{"version": "'${VERSION}'", "ols_test_workers": 10}'
}

@test "orion daemon small scale cluster density with anomaly detection" {
  orion daemon --port 8080 &
  DAEMON_PID=$!
  echo "Orion daemon started with PID $DAEMON_PID"
  run_cmd curl http://127.0.0.1:8080/daemon/anomaly?convert_tinyurl=True&test_name=small-scale-cluster-density
  if [ ! -z "$DAEMON_PID" ]; then
    kill $DAEMON_PID
    echo "Orion daemon with PID $DAEMON_PID killed"
  fi
}

@test "orion daemon small scale node density cni with changepoint detection" {
  orion daemon --port 8080 &
  DAEMON_PID=$!
  echo "Orion daemon started with PID $DAEMON_PID"
  run_cmd curl http://127.0.0.1:8080/daemon/changepoint?filter_changepoints=true&test_name=small-scale-node-density-cni
  if [ ! -z "$DAEMON_PID" ]; then
    kill $DAEMON_PID
    echo "Orion daemon with PID $DAEMON_PID killed"
  fi
}

@test "orion daemon trt payload cluster density with version parameter" {
  orion daemon --port 8080 &
  DAEMON_PID=$!
  echo "Orion daemon started with PID $DAEMON_PID"
  run_cmd curl http://127.0.0.1:8080/daemon/changepoint?version=$version&filter_changepoints=false&test_name=trt-payload-cluster-density
  if [ ! -z "$DAEMON_PID" ]; then
    kill $DAEMON_PID
    echo "Orion daemon with PID $DAEMON_PID killed"
  fi
}

@test "orion cmd with netobserv configs" {
  curl -s https://raw.githubusercontent.com/openshift-eng/ocp-qe-perfscale-ci/refs/heads/netobserv-perf-tests/scripts/queries/netobserv-orion-node-density-heavy.yaml -w %{http_code} -o /tmp/netobserv-node-density-heavy-ospst.yaml
  run_cmd orion cmd --config "/tmp/netobserv-node-density-heavy-ospst.yaml" --lookback 5d --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"workers": 25}'
}


