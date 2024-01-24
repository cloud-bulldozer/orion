# Orion - CLI tool to find regressions
Orion stands as a powerful command-line tool designed for identifying regressions within perf-scale CPT runs, leveraging metadata provided during the process. The detection mechanism relies on [hunter](https://github.com/datastax-labs/hunter).

Below is an illustrative example of the config and metadata that Orion can handle:

```
tests :
  - name : aws-small-scale-cluster-density-v2
    platform: AWS
    masterNodesType: m6a.xlarge
    masterNodesCount: 3
    workerNodesType: m6a.xlarge
    workerNodesCount: 24
    benchmark: cluster-density-v2
    ocpVersion: 4.15
    networkType: OVNKubernetes
    # encrypted: true
    # fips: false
    # ipsec: false

    metrics : 
    - metric : podReadyLatency
      metricType : latency
      
    - metric : apiserverCPU
      metricType : cpu
      namespace: openshift-kube-apiserver

    - metric: ovnCPU
      metricType: cpu
      namespace: openshift-ovn-kubernetes
    
    - metric: etcdCPU
      metricType: cpu
      namespace: openshift-ovn-kubernetes


```

## Build Orion
Building Orion is a straightforward process. Follow these commands:

Clone the current repository using git clone.

```
>> git clone <repository_url>
>> pip install venv
>> source venv/bin/activate
>> pip install -r requirements.txt
>> export ES_SERVER = <es_server_url>
>> pip install .
```
## Run Orion
Executing Orion is as simple as building it. After following the build steps, run the following:
```
>> orion
```
At the moment, 

Orion provides flexibility in configuring its behavior by allowing users to set the path to their config file using the ```--config``` flag. 

For enhanced troubleshooting and debugging, Orion supports the ```--debug``` flag, enabling the generation of detailed debug logs. 

Additionally, users can specify a custom path for the output CSV file using the ```--output``` flag, providing control over the location where the generated CSV will be stored.

Orion's seamless integration with metadata and hunter ensures a robust regression detection tool for perf-scale CPT runs.


