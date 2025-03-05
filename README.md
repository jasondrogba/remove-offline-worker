# remove-offline-worker

## 主要针对的修复场景
k8s node意外崩溃，首先是node 状态变成 NotReady，同时在其他pod ping该节点的worker ip会失败。但是该节点的worker pod状态仍然是Running。且worker状态是ONLINE，etcd中需要等待片刻之后才会移除该worker id。
等待大概几分钟后该节点的worker pod状态变成terminating，同时在新的节点上启动新的worker pod。之后原来worker pod状态会一直处于terminating。

## 脚本运行方案

定时监测node和worker pod状态，如果node状态是NotReady，那么找到对应的worker pod（通过node匹配）直接删除这个worker pod，同时根据这个worker pod ip，去etcd中删除/ServiceDiscovery/和/DHT。

## 如何运行
首先需要在脚本中填写正确的信息。
```
# 配置环境变量
# alluxio集群的namespace
ALLUXIO_NAMESPACE = "default"
# alluxio集群的名字，用于在etcd中匹配worker信息进行删除
ALLUXIO_NAME = "alluxio"
# 会进入到etcd pod中删除worker信息
ETCD_POD = "alluxio-etcd-0"
# 会进入到coordinator pod 中执行alluxio info nodes命令，可以换成其他正常running的worker pod
COORDINATOR_POD = "alluxio-coordinator-0"

# 日志信息保存的地方
LOG_FILE = "worker-monitor.log"
LOG_MAX_SIZE = 5 * 1024 * 1024  # 5MB
LOG_BACKUP_COUNT = 5  # 最多保留5个日志文件

# 定时执行的时间，每隔多长时间监测node，worker状态
CHECK_INTERVAL = 30  # 每30秒检查一次
```

在后台运行监控程序
```
nohup python3 monitor-remove-offline-worker.py > /dev/null 2>&1 &
```

## 正常日志
没有节点发生异常，所有pod都是running
```
[2025-03-05 15:41:26] ==================== Starting new check cycle ====================
[2025-03-05 15:41:27] Not Ready Nodes: []
[2025-03-05 15:41:27] Worker Pods: 
[2025-03-05 15:41:27]   alluxio-worker-577545dc9-2q7z7 on alluxio-e2e-worker3 (IP: 10.244.4.5) Status: Running
[2025-03-05 15:41:27]   alluxio-worker-577545dc9-6hjj9 on alluxio-e2e-worker2 (IP: 10.244.1.14) Status: Running
```

## 异常日志
有节点异常，状态是notReady，这时候进行脚本自动监测和处理的逻辑
```
[2025-03-05 15:44:28] ==================== Starting new check cycle ====================
[2025-03-05 15:44:28] Not Ready Nodes: ['alluxio-e2e-worker3']
[2025-03-05 15:44:28] Worker Pods: 
[2025-03-05 15:44:28]   alluxio-worker-577545dc9-2q7z7 on alluxio-e2e-worker3 (IP: 10.244.4.5) Status: Running
[2025-03-05 15:44:28]   alluxio-worker-577545dc9-6hjj9 on alluxio-e2e-worker2 (IP: 10.244.1.14) Status: Running
[2025-03-05 15:44:28] Pod alluxio-worker-577545dc9-2q7z7 is on NotReady node alluxio-e2e-worker3, deleting it.
[2025-03-05 15:45:53] Removing worker worker-0d950643-73c0-461d-a694-ecc601819336 from etcd
Defaulted container "etcd" out of: etcd, volume-permissions (init)
0
1
[2025-03-05 15:45:53] Deleting pod alluxio-worker-577545dc9-2q7z7
Warning: Immediate deletion does not wait for confirmation that the running resource has been terminated. The resource may continue to run on the cluster indefinitely.
pod "alluxio-worker-577545dc9-2q7z7" force deleted
```

监控脚本会首先去etcd中会删除对应的 `worker-0d950643-73c0-461d-a694-ecc601819336`
```
I have no name!@alluxio-etcd-0:/opt/bitnami/etcd$ etcdctl get --prefix "" | grep /ServiceDiscovery/
/ServiceDiscovery/default-alluxio/worker-0d950643-73c0-461d-a694-ecc601819336
/ServiceDiscovery/default-alluxio/worker-bd310c49-815f-4f7b-8948-1709dadb86f9
I have no name!@alluxio-etcd-0:/opt/bitnami/etcd$ etcdctl get --prefix "" | grep /ServiceDiscovery/
/ServiceDiscovery/default-alluxio/worker-bd310c49-815f-4f7b-8948-1709dadb86f9
```

然后监控脚本同时会强制delete 这个worker pod, 删除后会启动新的worker
```
➜  ~ kubectl get pods -w  -owide
NAME                                READY   STATUS    RESTARTS      AGE     IP            NODE                  NOMINATED NODE   READINESS GATES
alluxio-coordinator-0               1/1     Running   0             4h56m   10.244.1.15   alluxio-e2e-worker2   <none>           <none>
alluxio-etcd-0                      1/1     Running   0             4h56m   10.244.1.16   alluxio-e2e-worker2   <none>           <none>
alluxio-grafana-66b76fd4fb-5dfrm    1/1     Running   1 (13m ago)   60m     10.244.4.2    alluxio-e2e-worker3   <none>           <none>
alluxio-prometheus-974f6d98-7g24g   1/1     Running   0             3h50m   10.244.1.17   alluxio-e2e-worker2   <none>           <none>
alluxio-worker-577545dc9-2q7z7      1/1     Running   0             4m31s   10.244.4.5    alluxio-e2e-worker3   <none>           <none>
alluxio-worker-577545dc9-6hjj9      1/1     Running   0             4h56m   10.244.1.14   alluxio-e2e-worker2   <none>           <none>
busybox                             1/1     Running   0             2m37s   10.244.4.6    alluxio-e2e-worker3   <none>           <none>
alluxio-worker-577545dc9-2q7z7      1/1     Running   0             30m     10.244.4.5    alluxio-e2e-worker3   <none>           <none>
alluxio-grafana-66b76fd4fb-5dfrm    1/1     Running   1 (39m ago)   87m     10.244.4.2    alluxio-e2e-worker3   <none>           <none>
busybox                             1/1     Running   0             28m     10.244.4.6    alluxio-e2e-worker3   <none>           <none>
alluxio-worker-577545dc9-2q7z7      1/1     Terminating   0             32m     10.244.4.5    alluxio-e2e-worker3   <none>           <none>
alluxio-worker-577545dc9-2q7z7      1/1     Terminating   0             32m     10.244.4.5    alluxio-e2e-worker3   <none>           <none>
alluxio-worker-577545dc9-ltztk      0/1     Pending       0             0s      <none>        <none>                <none>           <none>
alluxio-worker-577545dc9-ltztk      0/1     Pending       0             0s      <none>        alluxio-e2e-worker    <none>           <none>
alluxio-worker-577545dc9-ltztk      0/1     Init:0/2      0             0s      <none>        alluxio-e2e-worker    <none>           <none>
alluxio-worker-577545dc9-ltztk      0/1     Init:1/2      0             1s      10.244.2.3    alluxio-e2e-worker    <none>           <none>
alluxio-worker-577545dc9-ltztk      0/1     PodInitializing   0             2s      10.244.2.3    alluxio-e2e-worker    <none>           <none>
alluxio-worker-577545dc9-ltztk      0/1     Running           0             3s      10.244.2.3    alluxio-e2e-worker    <none>           <none>
alluxio-worker-577545dc9-ltztk      0/1     Running           0             61s     10.244.2.3    alluxio-e2e-worker    <none>           <none>
alluxio-worker-577545dc9-ltztk      1/1     Running           0             61s     10.244.2.3    alluxio-e2e-worker    <none>           <none>
```

删除异常节点的worker，并且从etcd中移除了worker，日志恢复正常，因为worker pod已经重新启动在另外的节点上了，异常的node上没有worker pod。
```
[2025-03-05 15:46:23] ==================== Starting new check cycle ====================
[2025-03-05 15:46:23] Not Ready Nodes: ['alluxio-e2e-worker3']
[2025-03-05 15:46:23] Worker Pods: 
[2025-03-05 15:46:23]   alluxio-worker-577545dc9-6hjj9 on alluxio-e2e-worker2 (IP: 10.244.1.14) Status: Running
[2025-03-05 15:46:23]   alluxio-worker-577545dc9-ltztk on alluxio-e2e-worker (IP: 10.244.2.3) Status: Running
[2025-03-05 15:46:53] ==================== Starting new check cycle ====================
```