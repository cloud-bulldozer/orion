#!/bin/bash

# Function to run a command and handle specific exit codes
run_cmd(){
  echo "$@"
  ${@}
  EXIT_CODE=$?

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

run_cmd orion cmd --config "examples/readout-control-plane-cdv2.yaml" --hunter-analyze --output-format text --save-output-path=output.txt
