#!/usr/bin/env bats
# vi: ft=bash
# shellcheck disable=SC2086,SC2030,SC2031,SC2164
#
# Local integration tests — runs against any OpenSearch instance populated
# with hack/ci-tests/ data.  No private-ES version discovery needed.


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
  ES_SERVER="${QE_ES_SERVER:-http://localhost:9200}"
  mkdir -p outputs
}

# ---------------------------------------------------------------------------
# Version check (no ES required)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# hunter-analyze (text / json / junit)
# ---------------------------------------------------------------------------

@test "orion with regression should contain inline changepoint" {
  set +e
  orion --lookback 15d --since 2026-01-20 --hunter-analyze --config hack/ci-tests/configurations/ci-tests.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' > ./outputs/results.txt
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  if ! grep -q "+404.5%" ./outputs/results.txt; then
    echo "Expected string '+404.5%' not found in results.txt"
    exit 1
  fi

  if ! grep -q "Previous version:    4.20.0-0.nightly-2026-01-14-195655" ./outputs/results.txt; then
    echo "Expected string 'Previous version:    4.20.0-0.nightly-2026-01-14-195655' not found in results.txt"
    exit 1
  fi

  if ! grep -q "Changepoint at:      4.20.0-0.nightly-2026-01-15-195655" ./outputs/results.txt; then
    echo "Expected string 'Changepoint at:      4.20.0-0.nightly-2026-01-15-195655' not found in results.txt"
    exit 1
  fi

  set -e
}

@test "orion with regression should contain inline changepoint json" {
  set +e

  orion --lookback 15d --since 2026-01-20 --hunter-analyze --config hack/ci-tests/configurations/ci-tests.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' --output-format json --save-output-path=./outputs/results.json
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  bad_version=$(jq -r '.[] | select(.is_changepoint == true) | .ocpVersion' ./outputs/results_olm-integration-test.json)

  if [ "$bad_version" != "4.20.0-0.nightly-2026-01-15-195655" ]; then
    echo "Version did not match. Expected '4.20.0-0.nightly-2026-01-15-195655', got '$bad_version'"
    exit 1
  fi
  set -e
}

@test "orion with regression should contain inline changepoint junit" {
  set +e

  orion --lookback 15d --since 2026-01-20 --hunter-analyze --config hack/ci-tests/configurations/ci-tests.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' --output-format junit --save-output-path=./outputs/results.xml
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  failure=$(echo 'failures="1"')
  if ! grep -q $failure ./outputs/results_olm-integration-test.xml; then
    echo "Expected string '$failure' not found in results_olm-integration-test.xml"
    cat ./outputs/results_olm-integration-test.xml
    exit 1
  fi

  changepoint=$(echo '404.549 | https://prow.ci/2013174937652563968 | -- changepoint')
  if ! grep -q $changepoint ./outputs/results_olm-integration-test.xml; then
    echo "Expected string '$changepoint' not found in results_olm-integration-test.xml"
    cat ./outputs/results_olm-integration-test.xml
    exit 1
  fi

  set -e
}

# ---------------------------------------------------------------------------
# hunter-analyze with custom display
# ---------------------------------------------------------------------------

@test "orion with regression should contain inline changepoint with custom display" {
  set +e

  orion --lookback 15d --since 2026-01-20 --hunter-analyze --config hack/ci-tests/configurations/ci-tests.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' --display upstreamJob > ./outputs/results.txt
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  if ! grep -q "+404.5%" ./outputs/results.txt; then
    echo "Expected string '+404.5%' not found in results.txt"
    cat ./outputs/results.txt
    exit 1
  fi

  if ! grep -q "Previous version:    4.20.0-0.nightly-2026-01-14-195655" ./outputs/results.txt; then
    echo "Expected string 'Previous version:    4.20.0-0.nightly-2026-01-14-195655' not found in results.txt"
    cat ./outputs/results.txt
    exit 1
  fi

  if ! grep -q "Changepoint at:      4.20.0-0.nightly-2026-01-15-195655" ./outputs/results.txt; then
    echo "Expected string 'Changepoint at:      4.20.0-0.nightly-2026-01-15-195655' not found in results.txt"
    cat ./outputs/results.txt
    exit 1
  fi

  customDisplay="upstreamJob"
  if ! grep -q $customDisplay ./outputs/results.txt; then
    echo "Expected string '$customDisplay' not found in results.txt"
    cat ./outputs/results.txt
    exit 1
  fi

  set -e
}

@test "orion with regression should contain inline changepoint json with custom display" {
  set +e

  orion --lookback 15d --since 2026-01-20 --hunter-analyze --config hack/ci-tests/configurations/ci-tests.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' --output-format json --display upstreamJob --save-output-path=./outputs/results.json
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  bad_version=$(jq -r '.[] | select(.is_changepoint == true) | .ocpVersion' ./outputs/results_olm-integration-test.json)
  if [ "$bad_version" != "4.20.0-0.nightly-2026-01-15-195655" ]; then
    echo "Version did not match. Expected '4.20.0-0.nightly-2026-01-15-195655', got '$bad_version'"
    exit 1
  fi

  upstreamJob=$(jq -r '.[] | select(.is_changepoint == true) | .upstreamJob' ./outputs/results_olm-integration-test.json)
  if [ "$upstreamJob" != "periodic-ci-openshift-eng-ocp-qe-perfscale-ci-main-gcp-4.20-nightly-x86-olmv1-benchmark-test" ]; then
    echo "upstreamJob did not match. Expected 'periodic-ci-openshift-eng-ocp-qe-perfscale-ci-main-gcp-4.20-nightly-x86-olmv1-benchmark-test', got '$upstreamJob'"
    exit 1
  fi

  set -e
}

@test "orion with regression should contain inline changepoint junit with custom display" {
  set +e

  orion --lookback 15d --since 2026-01-20 --hunter-analyze --config hack/ci-tests/configurations/ci-tests.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' --output-format junit --display upstreamJob --save-output-path=./outputs/results.xml
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  failure=$(echo 'failures="1"')
  if ! grep -q $failure ./outputs/results_olm-integration-test.xml; then
    echo "Expected string '$failure' not found in results_olm-integration-test.xml"
    cat ./outputs/results_olm-integration-test.xml
    exit 1
  fi

  changepoint=$(echo '404.549')
  if ! grep -q $changepoint ./outputs/results_olm-integration-test.xml; then
    echo "Expected string '$changepoint' not found in results_olm-integration-test.xml"
    cat ./outputs/results_olm-integration-test.xml
    exit 1
  fi

  customDisplay="upstreamJob"
  if ! grep -q $customDisplay ./outputs/results_olm-integration-test.xml; then
    echo "Expected string '$customDisplay' not found in results_olm-integration-test.xml"
    cat ./outputs/results_olm-integration-test.xml
    exit 1
  fi

  set -e
}

# ---------------------------------------------------------------------------
# No metadata index
# ---------------------------------------------------------------------------

@test "orion with regression should contain inline changepoint no metadata index" {
  set +e
  orion --lookback 15d --since 2026-01-20 --hunter-analyze --config hack/ci-tests/configurations/ci-tests-metrics-only.yaml --metadata-index "orion-integration-test-metrics*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' > ./outputs/results.txt
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  if ! grep -q "+404.5%" ./outputs/results.txt; then
    echo "Expected string '+404.5%' not found in results.txt"
    exit 1
  fi

  if ! grep -q "Previous version:    4.20" ./outputs/results.txt; then
    echo "Expected string 'Previous version:    4.20' not found in results.txt"
    exit 1
  fi

  if ! grep -q "Changepoint at:      4.20" ./outputs/results.txt; then
    echo "Expected string 'Changepoint at:      4.20' not found in results.txt"
    exit 1
  fi

  set -e
}

# ---------------------------------------------------------------------------
# Early changepoint
# ---------------------------------------------------------------------------

@test "orion early-changepoint metric - changepoint in first 5 is skipped when expansion finds no extra data" {
  set +e
  orion --lookback 15d --since 2026-01-20 --hunter-analyze --config hack/ci-tests/configurations/ci-tests-early-cp.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' > ./outputs/results-early-cp.txt
  EXIT_CODE=$?

  if [ $EXIT_CODE -eq 2 ]; then
    echo "Regression was reported but should be skipped (no extra data after expansion)"
    cat ./outputs/results-early-cp.txt
    exit 1
  fi

  if grep -q "Bad Version:         4.20.0-0.nightly-2026-01-14-195655" ./outputs/results-early-cp.txt; then
    echo "Expected early changepoint to be skipped (no Bad Version in output)"
    cat ./outputs/results-early-cp.txt
    exit 1
  fi

  set -e
}

# ---------------------------------------------------------------------------
# Anomaly detection (text / json / junit)
# ---------------------------------------------------------------------------

@test "orion --anomaly-detection with regression should contain inline changepoint" {
  set +e
  orion --lookback 15d --since 2026-01-20 --anomaly-detection --config hack/ci-tests/configurations/ci-tests.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' > ./outputs/results-anomaly.txt
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  if ! grep -q "+155.6%" ./outputs/results-anomaly.txt; then
    echo "Expected string '+155.6%' not found in results.txt"
    exit 1
  fi

  if ! grep -q "+56.7%" ./outputs/results-anomaly.txt; then
    echo "Expected string '+56.7%' not found in results.txt"
    exit 1
  fi

  if ! grep -q "+38.9%" ./outputs/results-anomaly.txt; then
    echo "Expected string '+38.9%' not found in results.txt"
    exit 1
  fi

  if ! grep -q "Changepoint at:      4.20.0-0.nightly-2026-01-15-195655" ./outputs/results-anomaly.txt; then
    echo "Expected string 'Changepoint at:      4.20.0-0.nightly-2026-01-15-195655' not found in results.txt"
    exit 1
  fi

  if ! grep -q "Changepoint at:      4.20.0-0.nightly-2026-01-17-195655" ./outputs/results-anomaly.txt; then
    echo "Expected string 'Changepoint at:      4.20.0-0.nightly-2026-01-17-195655' not found in results.txt"
    exit 1
  fi

  set -e
}


@test "orion --anomaly-detection with regression should contain inline changepoint json" {
  set +e
  orion --lookback 15d --since 2026-01-20 --anomaly-detection --config hack/ci-tests/configurations/ci-tests.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' --output-format json --save-output-path=./outputs/results-anomaly.json
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  CHANGEPOINTS=$(grep -c '"is_changepoint": true' ./outputs/results-anomaly_olm-integration-test.json)
  if [ "$CHANGEPOINTS" -ne 3 ]; then
    echo "Expected 3 changepoints, found $CHANGEPOINTS in ./outputs/results-anomaly_olm-integration-test.json"
    exit 1
  fi

  set -e
}

@test "orion --anomaly-detection with regression should contain inline changepoint junit" {
  set +e
  orion --lookback 15d --since 2026-01-20 --anomaly-detection --config hack/ci-tests/configurations/ci-tests.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' --output-format junit --save-output-path=./outputs/results-anomaly.xml
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  if ! grep -q "155.648" ./outputs/results-anomaly_olm-integration-test.xml; then
    echo "Expected string '155.648' not found in ./outputs/results-anomaly_olm-integration-test.xml"
    exit 1
  fi

  if ! grep -q "56.7208" ./outputs/results-anomaly_olm-integration-test.xml; then
    echo "Expected string '56.7208' not found in ./outputs/results-anomaly_olm-integration-test.xml"
    exit 1
  fi

  if ! grep -q "38.8858" ./outputs/results-anomaly_olm-integration-test.xml; then
    echo "Expected string '38.8858' not found in ./outputs/results-anomaly_olm-integration-test.xml"
    exit 1
  fi

  set -e
}

# ---------------------------------------------------------------------------
# CMR (text / json / junit)
# ---------------------------------------------------------------------------

@test "orion --cmr with regression should contain inline changepoint" {
  set +e
  orion --lookback 15d --since 2026-01-20 --cmr --config hack/ci-tests/configurations/ci-tests.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' > ./outputs/results-cmr.txt
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  if ! grep -q "+160.9%" ./outputs/results-cmr.txt; then
    echo "Expected string '+160.9%' not found in results-cmr.txt"
    exit 1
  fi

  set -e
}

@test "orion --cmr with regression should contain inline changepoint json" {
  set +e
  orion --lookback 15d --since 2026-01-20 --cmr --config hack/ci-tests/configurations/ci-tests.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' --output-format json --save-output-path=./outputs/results-cmr.json
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  bad_version=$(jq -r '.[] | select(.is_changepoint == true) | .ocpVersion' ./outputs/results-cmr_olm-integration-test.json)
  if [ "$bad_version" != "4.20.0-0.nightly-2026-01-18-195655" ]; then
    echo "Version did not match. Expected '4.20.0-0.nightly-2026-01-18-195655', got '$bad_version'"
    exit 1
  fi

  set -e
}

@test "orion --cmr with regression should contain inline changepoint junit" {
  set +e
  orion --lookback 15d --since 2026-01-20 --cmr --config hack/ci-tests/configurations/ci-tests.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' --output-format junit --save-output-path=./outputs/results-cmr.xml
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  if ! grep -q "True             |             160.879" ./outputs/results-cmr_olm-integration-test.xml; then
    echo "Expected string 'True             |             160.879' not found in results-cmr_olm-integration-test.xml"
    exit 1
  fi

  set -e
}

# ---------------------------------------------------------------------------
# Config inheritance
# ---------------------------------------------------------------------------

@test "orion inheriting config" {
  set +e
  orion --lookback 15d --since 2026-01-20 --hunter-analyze --config hack/ci-tests/configurations/ci-tests-inherits.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' > ./outputs/results.txt
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  if ! grep -q "OCP-84094_catalogdCPU_GCP_sum_sum" ./outputs/results.txt; then
    echo "Expected string 'OCP-84094_catalogdCPU_GCP_sum_sum' not found in results.txt"
    exit 1
  fi

  if ! grep -q "+404.5%" ./outputs/results.txt; then
    echo "Expected string '+404.5%' not found in results.txt"
    exit 1
  fi

  if ! grep -q "Previous version:    4.20.0-0.nightly-2026-01-14-195655" ./outputs/results.txt; then
    echo "Expected string 'Previous version:    4.20.0-0.nightly-2026-01-14-195655' not found in results.txt"
    exit 1
  fi

  if ! grep -q "Changepoint at:      4.20.0-0.nightly-2026-01-15-195655" ./outputs/results.txt; then
    echo "Expected string 'Changepoint at:      4.20.0-0.nightly-2026-01-15-195655' not found in results.txt"
    exit 1
  fi

  set -e
}

@test "orion inheriting config ignore global" {
  set +e
  orion --lookback 15d --since 2026-01-20 --hunter-analyze --config hack/ci-tests/configurations/ci-tests-inherits-ignore-global.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' > ./outputs/results.txt
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  if grep -q "OCP-84094_catalogdCPU_GCP_sum_sum" ./outputs/results.txt; then
    echo "Expected string 'OCP-84094_catalogdCPU_GCP_sum_sum' found in results.txt, should not be present"
    exit 1
  fi

  if ! grep -q "OCP-84094_catalogdCPU_GCP_avg" ./outputs/results.txt; then
    echo "Expected string 'OCP-84094_catalogdCPU_GCP_avg' not found in results.txt"
    exit 1
  fi

  set -e
}

@test "orion inheriting config local metadata" {
  set +e
  orion --lookback 15d --since 2026-01-20 --hunter-analyze --config hack/ci-tests/configurations/ci-tests-inherits-local-metadata.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' > ./outputs/results.txt
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 3 ]; then
    echo "no regression found"
    exit 1
  fi
}

@test "orion inheriting config local metrics with global ignore" {
  set +e
  orion --lookback 15d --since 2026-01-20 --hunter-analyze --config hack/ci-tests/configurations/ci-tests-inherits-local-metrics-with-ignore.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' > ./outputs/results.txt
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  if ! grep -q "OCP-84094_catalogdCPU_GCP_max_max" ./outputs/results.txt; then
    echo "Expected string 'OCP-84094_catalogdCPU_GCP_max_max' not found in results.txt"
    exit 1
  fi

  if grep -q "OCP-84094_catalogdCPU_GCP_sum_sum" ./outputs/results.txt; then
    echo "Expected string 'OCP-84094_catalogdCPU_GCP_sum_sum' found in results.txt, should not be present"
    exit 1
  fi

  if ! grep -q "OCP-84094_catalogdCPU_GCP_avg" ./outputs/results.txt; then
    echo "Expected string 'OCP-84094_catalogdCPU_GCP_avg' not found in results.txt"
    exit 1
  fi

  set -e
}

@test "orion inheriting config local metrics" {
  set +e
  orion --lookback 15d --since 2026-01-20 --hunter-analyze --config hack/ci-tests/configurations/ci-tests-inherits-local-metrics.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' > ./outputs/results.txt
  EXIT_CODE=$?

  if [ ! $EXIT_CODE -eq 2 ]; then
    echo "no regression found"
    exit 1
  fi

  if ! grep -q "OCP-84094_catalogdCPU_GCP_max_max" ./outputs/results.txt; then
    echo "Expected string 'OCP-84094_catalogdCPU_GCP_max_max' not found in results.txt"
    exit 1
  fi

  if ! grep -q "OCP-84094_catalogdCPU_GCP_sum_sum" ./outputs/results.txt; then
    echo "Expected string 'OCP-84094_catalogdCPU_GCP_sum_sum' not found in results.txt"
    exit 1
  fi

  if ! grep -q "OCP-84094_catalogdCPU_GCP_avg" ./outputs/results.txt; then
    echo "Expected string 'OCP-84094_catalogdCPU_GCP_avg' not found in results.txt"
    exit 1
  fi

  set -e
}

# ---------------------------------------------------------------------------
# ACK auto-load
# ---------------------------------------------------------------------------

@test "orion auto-loads ack/all_ack.yaml when present" {
  set +e
  orion --lookback 15d --since 2026-01-20 --hunter-analyze --config hack/ci-tests/configurations/ci-tests.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --es-server=${ES_SERVER} --node-count true --input-vars='{"version": "4.20"}' 2>&1 | tee ./outputs/results-ack-auto.txt
  EXIT_CODE=$?
  set -e
  if [ ! -f ack/all_ack.yaml ]; then
    skip "ack/all_ack.yaml not present, skipping auto-load test"
  fi
  if ! grep -q "all_ack.yaml" ./outputs/results-ack-auto.txt; then
    echo "Expected orion to mention all_ack.yaml when auto-loading ACK"
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Browbeat / RHOSO
# ---------------------------------------------------------------------------

@test "orion browbeat config should contain keystone metrics text" {
  set +e
  orion --lookback 15d --hunter-analyze --config hack/ci-tests/configurations/ci-tests-browbeat.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --since 2026-02-23 --display='' --input-vars='{"version": "4.18"}' --es-server=${ES_SERVER} > ./outputs/results-browbeat.txt
  set -e

  for metric in keystone_v3_list_users_avg_avg keystone_v3_list_users_count_count keystone_v3_list_users_P99_percentiles keystone_v3_list_users_P95_percentiles keystone_v3_list_users_P90_percentiles keystone_v3_list_users_max_max keystone_v3_list_users_min_min keystone_v3_list_users_sum_sum; do
    if ! grep -q "$metric" ./outputs/results-browbeat.txt; then
      echo "Expected metric '$metric' not found in results-browbeat.txt"
      exit 1
    fi
  done
}

@test "orion browbeat config should contain keystone metrics json" {
  set +e
  orion --lookback 15d --hunter-analyze --config hack/ci-tests/configurations/ci-tests-browbeat.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --since 2026-02-23 --display='' --input-vars='{"version": "4.18"}' --es-server=${ES_SERVER} --output-format json > ./outputs/results-browbeat.json
  set -e

  for metric in keystone_v3_list_users_avg_avg keystone_v3_list_users_count_count keystone_v3_list_users_P99_percentiles keystone_v3_list_users_P95_percentiles keystone_v3_list_users_P90_percentiles keystone_v3_list_users_max_max keystone_v3_list_users_min_min keystone_v3_list_users_sum_sum; do
    if ! grep -q "$metric" ./outputs/results-browbeat.json; then
      echo "Expected metric '$metric' not found in results-browbeat.json"
      exit 1
    fi
  done
}

@test "orion browbeat config should contain keystone metrics junit" {
  set +e
  orion --lookback 15d --hunter-analyze --config hack/ci-tests/configurations/ci-tests-browbeat.yaml --metadata-index "orion-integration-test-data*" --benchmark-index "orion-integration-test-metrics*" --since 2026-02-23 --display='' --input-vars='{"version": "4.18"}' --es-server=${ES_SERVER} --output-format junit > ./outputs/results-browbeat.xml
  set -e

  for metric in keystone_v3_list_users_avg_avg keystone_v3_list_users_count_count keystone_v3_list_users_P99_percentiles keystone_v3_list_users_P95_percentiles keystone_v3_list_users_P90_percentiles keystone_v3_list_users_max_max keystone_v3_list_users_min_min keystone_v3_list_users_sum_sum; do
    if ! grep -q "$metric" ./outputs/results-browbeat.xml; then
      echo "Expected metric '$metric' not found in results-browbeat.xml"
      exit 1
    fi
  done
}
