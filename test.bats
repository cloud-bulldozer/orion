#!/usr/bin/env bats
# vi: ft=bash
# shellcheck disable=SC2086,SC2030,SC2031,SC2164


check_file_list() {
  for f in "${@}"; do
    if [[ ! -f ${f} ]]; then
      echo "File ${f} not found"
      echo "Content of $(dirname ${f}):"
      ls -l "$(dirname ${f})"
      return 1
    fi
    if [[ $(jq .[0].metricName ${f}) == "" ]]; then
      echo "Incorrect format in ${f}"
      cat "${f}"
      return 1
    fi
  done
  return 0
}

run_cmd(){
  echo "$@"
  ${@}
}

setup() {
  export UUID; UUID=$(uuidgen)
}

@test "orion cmd label small scale cluster density with hunter-analyze" {
  export ES_METADATA_INDEX="ospst-perf-scale-ci-*"
  export ES_BENCHMARK_INDEX="ospst-ripsaw-kube-burner*"
  run_cmd orion cmd --config "examples/label-small-scale-cluster-density.yaml" --lookback 5d --hunter-analyze
}

@test "orion cmd payload scale 4.15" {
  export ES_METADATA_INDEX="ospst-perf-scale-ci-*"
  export ES_BENCHMARK_INDEX="ospst-ripsaw-kube-burner*"
  run_cmd orion cmd --config "examples/payload-scale-415.yaml" --lookback 5d
}

@test "orion cmd payload scale 4.16 without lookback period" {
  export ES_METADATA_INDEX="ospst-perf-scale-ci-*"
  export ES_BENCHMARK_INDEX="ospst-ripsaw-kube-burner*"
  run_cmd orion cmd --config "examples/payload-scale-416.yaml"
}

@test "orion cmd readout control plane cdv2 with text output" {
  export ES_METADATA_INDEX="ospst-perf-scale-ci-*"
  export ES_BENCHMARK_INDEX="ospst-ripsaw-kube-burner*"
  run_cmd orion cmd --config "examples/readout-control-plane-cdv2.yaml" --lookback 5d --hunter-analyze --output-format text --save-output-path=output.txt
  check_file_list output_cluster-density-v2-24nodes.txt
}

@test "orion cmd readout control plane node-density with json output" {
  export ES_METADATA_INDEX="ospst-perf-scale-ci-*"
  export ES_BENCHMARK_INDEX="ospst-ripsaw-kube-burner*"
  run_cmd orion cmd --config "examples/readout-control-plane-node-density.yaml" --lookback 5d --hunter-analyze --output-format json --save-output-path=output.json
  check_file_list output_node-density-heavy-24nodes.json
}

@test "orion cmd readout netperf tcp with junit output" {
  run_cmd orion cmd --config "examples/readout-netperf-tcp.yaml" --lookback 5d --output-format junit --hunter-analyze --save-output-path=output.xml
  check_file_list output_k8s-netperf-tcp.xml
}

@test "orion cmd small scale cluster density with anamoly detection" {
  export ES_METADATA_INDEX="ospst-perf-scale-ci-*"
  export ES_BENCHMARK_INDEX="ospst-ripsaw-kube-burner*"
  run_cmd orion cmd --config "examples/small-scale-cluster-density.yaml" --lookback 5d --anamoly-detection 
}

@test "orion cmd small scale node density cni with anamoly detection with a window" {
  export ES_METADATA_INDEX="ospst-perf-scale-ci-*"
  export ES_BENCHMARK_INDEX="ospst-ripsaw-kube-burner*"
  run_cmd orion cmd --config "examples/small-scale-node-density-cni.yaml" --anamoly-detection --anamoly-window 3
}

@test "orion cmd trt external payload cluster density with anamoly detection with minimum percentage" {
  export ES_METADATA_INDEX="perf_scale_ci-*"
  export ES_BENCHMARK_INDEX="ripsaw-kube-burner*
  run_cmd orion cmd --config "examples/trt-external-payload-cluster-density.yaml" --anamoly-detection --anamoly-window 3 --min-anomaly-percent 5
}
