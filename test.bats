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
    return 1
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

}

@test "orion label small scale cluster density with hunter-analyze" {
  run_cmd orion --config "examples/label-small-scale-cluster-density.yaml" --lookback 5d --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion label small scale cluster density with hunter-analyze and using env vars for ES" {
  export ES_SERVER=${ES_SERVER} es_metadata_index=${METADATA_INDEX} es_benchmark_index=${BENCHMARK_INDEX}
  run_cmd orion --config "examples/label-small-scale-cluster-density.yaml" --lookback 5d --hunter-analyze --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion payload scale" {
  run_cmd orion --config "examples/payload-scale.yaml" --lookback 5d --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
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
  run_cmd orion --config examples/metal-perfscale-cpt-virt-density.yaml --lookback 15d --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion small scale cluster density with anomaly detection" {
  run_cmd orion --config "examples/small-scale-cluster-density.yaml" --lookback 5d --anomaly-detection --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
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

@test "orion trt external payload cluster density" {
  run_cmd orion --config "examples/trt-payload-cluster-density.yaml" --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"version": "'${VERSION}'"}'
}

@test "orion chaos tests " {
  before_version=$version
  scenario_type="pvc_scenarios" cloud_infrastructure="aws" cloud_type="self-managed" total_node_count="9" node_instance_type="m6a.xlarge" network_plugins="OVNKubernetes" scenario_file="*pvc_scenario.yaml" run_cmd orion --config "examples/chaos_tests.yaml" --lookback 10d --es-server=${ES_SERVER} --metadata-index=${KRKEN_METADATA_INDEX} --benchmark-index=${KRKN_BENCHMARK_INDEX} --input-vars='{"version": "'${chaos_version}'"}'  --output text
  VERSION=$before_version
}

@test "orion node scenarios " {
  before_version=$version
  VERSION=$chaos_version
  scenario_type="node_scenarios" cloud_infrastructure="AWS" cloud_type="self-managed" total_node_count="9" node_instance_type="*xlarge*" network_plugins="OVNKubernetes" scenario_file="*node_scenario.yaml" run_cmd orion --config "examples/node_scenarios.yaml" --lookback 10d --es-server=${ES_SERVER} --metadata-index=${KRKEN_METADATA_INDEX} --benchmark-index=${KRKN_BENCHMARK_INDEX}  --hunter-analyze
  VERSION=$before_version
}

@test "orion pod disruption scenarios " {
  before_version=$version
  VERSION=$chaos_version
  scenario_type="pod_disruption_scenarios" cloud_infrastructure="AWS" cloud_type="self-managed" total_node_count="9" node_instance_type="*xlarge*" network_plugins="OVNKubernetes" scenario_file="*pod_scenario.yaml" run_cmd orion --config "examples/pod_disruption_scenarios.yaml" --lookback 10d --es-server=${ES_SERVER} --metadata-index=${KRKEN_METADATA_INDEX} --benchmark-index=${KRKN_BENCHMARK_INDEX}
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
  curl -s https://raw.githubusercontent.com/openshift-eng/ocp-qe-perfscale-ci/refs/heads/netobserv-perf-tests/scripts/queries/netobserv-orion-node-density-heavy.yaml -w %{http_code} -o /tmp/netobserv-node-density-heavy-ospst.yaml
  run_cmd orion --config "/tmp/netobserv-node-density-heavy-ospst.yaml" --lookback 5d --hunter-analyze --es-server=${ES_SERVER} --metadata-index=${METADATA_INDEX} --benchmark-index=${BENCHMARK_INDEX} --input-vars='{"workers": 25}'
}


