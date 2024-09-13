#!/usr/bin/env bats
# vi: ft=bash
# shellcheck disable=SC2086,SC2030,SC2031,SC2164


run_cmd(){
  echo "$@"
  ${@}
}

setup() {
  # Make a note of daemon PID
  orion daemon --port 8080 &
  DAEMON_PID=$!
  echo "Orion daemon started with PID $DAEMON_PID"
  export ES_SERVER="$QE_ES_SERVER"
  export es_metadata_index="perf_scale_ci*"
  export es_benchmark_index="ripsaw-kube-burner*"
  export version='4.17'
}

@test "orion cmd label small scale cluster density with hunter-analyze " {
  run_cmd orion cmd --config "examples/label-small-scale-cluster-density.yaml" --lookback 5d --hunter-analyze
}

@test "orion cmd payload scale 4.15 " {
  run_cmd orion cmd --config "examples/payload-scale-415.yaml" --lookback 5d
}

@test "orion cmd payload scale 4.16 without lookback period " {
  run_cmd orion cmd --config "examples/payload-scale-416.yaml"
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
  run_cmd orion cmd --config "examples/readout-netperf-tcp.yaml" --output-format junit --hunter-analyze --save-output-path=output.xml
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

@test "orion daemon small scale cluster density with anomaly detection " {
  run_cmd curl http://127.0.0.1:8080/daemon/anomaly?convert_tinyurl=True&test_name=small-scale-cluster-density
}

@test "orion daemon small scale node density cni with changepoint detection " {
  run_cmd curl http://127.0.0.1:8080/daemon/changepoint?filter_changepoints=true&test_name=small-scale-node-density-cni
}

@test "orion daemon trt payload cluster density with version parameter " {
  run_cmd curl http://127.0.0.1:8080/daemon/changepoint?version=4.17&filter_changepoints=false&test_name=trt-payload-cluster-density
}

teardown() {
  # Kill the daemon using its PID
  if [ ! -z "$DAEMON_PID" ]; then
    kill $DAEMON_PID
    echo "Orion daemon with PID $DAEMON_PID killed"
  else
    echo "No daemon PID found"
  fi
}
