#!/usr/bin/env bats
# vi: ft=bash
# shellcheck disable=SC2086,SC2030,SC2031,SC2164


run_cmd(){
  echo "$@"
  set +e
  ${@}
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
  export ES_SERVER="$QE_ES_SERVER"
  export es_metadata_index="perf_scale_ci*"
  export es_benchmark_index="ripsaw-kube-burner*"
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
  export version=$(echo "$LATEST_VERSION" | cut -d. -f1,2)
}

@test "orion cmd label small scale cluster density with hunter-analyze " {
  run_cmd orion cmd --config "examples/label-small-scale-cluster-density.yaml" --lookback 5d --hunter-analyze
}

@test "orion cmd payload scale " {
  run_cmd orion cmd --config "examples/payload-scale.yaml" --lookback 5d --hunter-analyze
}

@test "orion cmd payload scale without lookback period " {
  run_cmd orion cmd --config "examples/payload-scale.yaml" --hunter-analyze
}

@test "orion cmd readout control plane cdv2 with text output " {
  run_cmd orion cmd --config "examples/readout-control-plane-cdv2.yaml" --hunter-analyze --output-format text --save-output-path=output.txt
}

@test "orion cmd readout control plane node-density with json output " {
  run_cmd orion cmd --config "examples/readout-control-plane-node-density.yaml" --hunter-analyze --output-format json --save-output-path=output.json
}

@test "orion cmd readout control plane node-density with json output and match all iterations " {
  run_cmd orion cmd --config "examples/readout-control-plane-node-density.yaml" --hunter-analyze --output-format json --save-output-path=output.json --node-count True
}

@test "orion cmd readout netperf tcp with junit output " {
  export es_benchmark_index="k8s-netperf"
  run_cmd orion cmd --config "examples/readout-netperf-tcp.yaml" --output-format junit --hunter-analyze --save-output-path=output.xml
}

@test "orion cmd virt-density " {
  run_cmd orion cmd --config examples/metal-perfscale-cpt-virt-density.yaml --lookback 15d --hunter-analyze
}

@test "orion cmd small scale cluster density with anomaly detection " {
  run_cmd orion cmd --config "examples/small-scale-cluster-density.yaml" --lookback 5d --anomaly-detection
}

@test "orion cmd small scale node density cni anomaly detection with a window " {
  run_cmd orion cmd --config "examples/small-scale-node-density-cni.yaml" --anomaly-detection --anomaly-window 3
}

@test "orion cmd trt external payload cluster density anomaly detection with a minimum percentage " {
  run_cmd orion cmd --config "examples/trt-external-payload-cluster-density.yaml" --anomaly-detection --anomaly-window 3 --min-anomaly-percent 5
}

@test "orion cmd trt external payload crd scale with default anomaly detection " {
  run_cmd orion cmd --config "examples/trt-external-payload-crd-scale.yaml" --anomaly-detection
}

@test "orion cmd trt external payload node density " {
  run_cmd orion cmd --config "examples/trt-external-payload-node-density.yaml" --hunter-analyze
}

@test "orion cmd trt external payload cluster density " {
  run_cmd orion cmd --config "examples/trt-payload-cluster-density.yaml" --hunter-analyze
}

@test "orion cmd chaos tests " {
  version="4.19" scenario_type="pvc_scenarios" cloud_infrastructure="aws" cloud_type="self-managed" total_node_count="9" node_instance_type="m6a.xlarge" network_plugins="OVNKubernetes" scenario_file="*pvc_scenario.yaml" run_cmd orion cmd --config "examples/chaos_tests.yaml" --lookback 10d
}

@test "orion cmd node scenarios " {
  version="4.19" scenario_type="node_scenarios" cloud_infrastructure="AWS" cloud_type="self-managed" total_node_count="9" node_instance_type="*xlarge*" network_plugins="OVNKubernetes" scenario_file="*node_scenario.yaml" run_cmd orion cmd --config "examples/node_scenarios.yaml" --lookback 10d
}

@test "orion cmd pod disruption scenarios " {
  version="4.19" scenario_type="pod_disruption_scenarios" cloud_infrastructure="AWS" cloud_type="self-managed" total_node_count="9" node_instance_type="*xlarge*" network_plugins="OVNKubernetes" scenario_file="*pod_disruption_scenario.yaml" run_cmd orion cmd --config "examples/pod_disruption_scenarios.yaml" --lookback 10d
}

@test "orion cmd ols configuration test " {
  export ols_test_workers=10
  es_metadata_index="perf_scale_ci*" es_benchmark_index="ols-load-test-results*" run_cmd orion cmd --config "examples/ols-load-generator.yaml" --hunter-analyze --ack ack/4.15_ols-load-generator-10w_ack.yaml
}

@test "orion daemon small scale cluster density with anomaly detection " {
  orion daemon --port 8080 &
  DAEMON_PID=$!
  echo "Orion daemon started with PID $DAEMON_PID"
  run_cmd curl http://127.0.0.1:8080/daemon/anomaly?convert_tinyurl=True&test_name=small-scale-cluster-density
  if [ ! -z "$DAEMON_PID" ]; then
    kill $DAEMON_PID
    echo "Orion daemon with PID $DAEMON_PID killed"
  fi
}

@test "orion daemon small scale node density cni with changepoint detection " {
  orion daemon --port 8080 &
  DAEMON_PID=$!
  echo "Orion daemon started with PID $DAEMON_PID"
  run_cmd curl http://127.0.0.1:8080/daemon/changepoint?filter_changepoints=true&test_name=small-scale-node-density-cni
  if [ ! -z "$DAEMON_PID" ]; then
    kill $DAEMON_PID
    echo "Orion daemon with PID $DAEMON_PID killed"
  fi
}

@test "orion daemon trt payload cluster density with version parameter " {
  orion daemon --port 8080 &
  DAEMON_PID=$!
  echo "Orion daemon started with PID $DAEMON_PID"
  run_cmd curl http://127.0.0.1:8080/daemon/changepoint?version=$version&filter_changepoints=false&test_name=trt-payload-cluster-density
  if [ ! -z "$DAEMON_PID" ]; then
    kill $DAEMON_PID
    echo "Orion daemon with PID $DAEMON_PID killed"
  fi
}

@test "orion cmd with netobserv configs " {
  curl -s https://raw.githubusercontent.com/openshift-eng/ocp-qe-perfscale-ci/refs/heads/netobserv-perf-tests/scripts/queries/netobserv-orion-node-density-heavy.yaml -w %{http_code} -o /tmp/netobserv-node-density-heavy-ospst.yaml
  export WORKERS=25
  run_cmd orion cmd --config "/tmp/netobserv-node-density-heavy-ospst.yaml" --lookback 5d --hunter-analyze
}


