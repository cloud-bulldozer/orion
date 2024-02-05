# Orion - CLI tool to find regressions
Orion stands as a powerful command-line tool designed for identifying regressions within perf-scale CPT runs, leveraging metadata provided during the process. The detection mechanism relies on [hunter](https://github.com/datastax-labs/hunter).

Below is an illustrative example of the config and metadata that Orion can handle:

```
tests :
  - name : aws-small-scale-cluster-density-v2
    metadata:
      platform: AWS
      masterNodesType: m6a.xlarge
      masterNodesCount: 3
      workerNodesType: m6a.xlarge
      workerNodesCount: 24
      benchmark.keyword: cluster-density-v2
      ocpVersion: 4.15
      networkType: OVNKubernetes
    # encrypted: true
    # fips: false
    # ipsec: false

    metrics : 
    - name:  podReadyLatency
      metricName: podLatencyQuantilesMeasurement
      quantileName: Ready
      metric_of_interest: P99
      not: 
        jobConfig.name: "garbage-collection"
      
    - name:  apiserverCPU
      metricName : containerCPU
      labels.namespace.keyword: openshift-kube-apiserver
      metric_of_interest: value
      agg:
        value: cpu
        agg_type: avg

    - name:  ovnCPU
      metricName : containerCPU
      labels.namespace.keyword: openshift-ovn-kubernetes
      metric_of_interest: value
      agg:
        value: cpu
        agg_type: avg

    - name:  etcdCPU
      metricName : containerCPU
      labels.namespace.keyword: openshift-etcd
      metric_of_interest: value
      agg:
        value: cpu
        agg_type: avg
    
    - name:  etcdDisck
      metricName : 99thEtcdDiskBackendCommitDurationSeconds
      metric_of_interest: value
      agg:
        value: duration
        agg_type: avg
        
```

## Build Orion
Building Orion is a straightforward process. Follow these commands:

**Note: Orion Compatibility**

Orion currently supports Python versions `3.8.x`, `3.9.x`, `3.10.x`, and `3.11.x`. Please be aware that using other Python versions might lead to dependency conflicts caused by hunter, creating a challenging situation known as "dependency hell." It's crucial to highlight that Python `3.12.x` may result in errors due to the removal of distutils, a dependency used by numpy. This information is essential to ensure a smooth experience with Orion and avoid potential compatibility issues.

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

Activate Orion's regression detection tool for performance-scale CPT runs effortlessly with the ```--hunter-analyze``` command. This seamlessly integrates with metadata and hunter, ensuring a robust and efficient regression detection process.

Additionally, users can specify a custom path for the output CSV file using the ```--output``` flag, providing control over the location where the generated CSV will be stored.



Orion's seamless integration with metadata and hunter ensures a robust regression detection tool for perf-scale CPT runs.


```--uuid``` : If you have a specific uuid in mind (maybe a current run), you can bypass the metadata configuration portion of the config file and use this paraemter. You will still need to specify a config file that contains a metrics section for the metrics you want to collect on the current uuid and uuids that match the metadata of the uuid configuration

```
tests :
  - name : current-uuid-etcd-duration
    metrics : 
    - name:  etcdDisck
      metricName : 99thEtcdDiskBackendCommitDurationSeconds
      metric_of_interest: value
      agg:
        value: duration
        agg_type: avg
```

Orion provides flexibility if you know the comparison uuid you want to compare among, use the ```--baseline``` flag. This should only be used in conjunction when setting uuid. Similar to the uuid section mentioned above, you'll have to set a metrics section to specify the data points you want to collect on

