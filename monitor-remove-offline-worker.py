import os
import time
import subprocess
from datetime import datetime
import re

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
CHECK_INTERVAL = 30  # 每30秒检查一次


def rotate_logs():
    """日志轮转，保留最多 LOG_BACKUP_COUNT 个日志文件"""
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) >= LOG_MAX_SIZE:
        for i in range(LOG_BACKUP_COUNT - 1, 0, -1):
            old_log = f"{LOG_FILE}.{i}"
            new_log = f"{LOG_FILE}.{i + 1}"
            if os.path.exists(old_log):
                os.rename(old_log, new_log)

        if os.path.exists(LOG_FILE):
            os.rename(LOG_FILE, f"{LOG_FILE}.1")


def log(message):
    """记录日志，并在日志文件过大时轮转"""
    rotate_logs()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)
    with open(LOG_FILE, "a") as f:
        f.write(log_entry + "\n")

def get_not_ready_nodes():
    """获取 NotReady 状态的节点列表"""
    result = subprocess.run(["kubectl", "get", "nodes"], capture_output=True, text=True)
    lines = result.stdout.split("\n")
    not_ready_nodes = [line.split()[0] for line in lines[1:] if "NotReady" in line]
    return not_ready_nodes

def get_worker_pods():
    """获取所有 worker pod 的状态信息"""
    result = subprocess.run([
        "kubectl", "get", "pods", "-owide", "-n", ALLUXIO_NAMESPACE,
        "-l", "app.kubernetes.io/component=worker"
    ], capture_output=True, text=True)
    lines = result.stdout.split("\n")
    worker_pods = []
    for line in lines[1:]:
        parts = re.split(r'\s{2,}', line.strip())  # 处理多空格分隔问题
        if len(parts) < 6:
            continue
        pod_name, status = parts[0], parts[2]
        ip, node = parts[-4], parts[-3]  # IP 和 Node 可能在倒数第三和倒数第二列
        worker_pods.append({"name": pod_name, "status": status, "ip": ip, "node": node})
    return worker_pods

def delete_pod(pod_name):
    """删除指定的 pod"""
    log(f"Deleting pod {pod_name}")
    subprocess.run(["kubectl", "delete", "pod", pod_name, "-n", ALLUXIO_NAMESPACE, "--force"])

def get_worker_id(pod_ip):
    """从 coordinator pod 执行 alluxio info nodes 获取 worker id"""
    result = subprocess.run([
        "kubectl", "exec", COORDINATOR_POD, "-n", ALLUXIO_NAMESPACE, "--", "alluxio", "info", "nodes"
    ], capture_output=True, text=True)
    lines = result.stdout.split("\n")
    for line in lines:
        if pod_ip in line:
            parts = line.split()
            if len(parts) > 1:
                return parts[0]  # 假设 worker ID 是该行的第一列
    return None

def delete_worker_from_etcd(worker_id):
    """从 etcd 中删除 worker 相关信息"""
    log(f"Removing worker {worker_id} from etcd")
    commands = (
        f"etcdctl del /ServiceDiscovery/{ALLUXIO_NAMESPACE}-{ALLUXIO_NAME}/{worker_id} && "
        f"etcdctl del /DHT/{ALLUXIO_NAMESPACE}-{ALLUXIO_NAME}/AUTHORIZED/{worker_id}"
    )
    subprocess.run(["kubectl", "exec", "-it", ETCD_POD, "-n", ALLUXIO_NAMESPACE, "--", "sh", "-c", commands])

def main():
    while True:
        log("==================== Starting new check cycle ====================")
        not_ready_nodes = get_not_ready_nodes()
        worker_pods = get_worker_pods()

        log(f"Not Ready Nodes: {not_ready_nodes}")
        log(f"Worker Pods: ")

        for pod in worker_pods:
            log(f"  {pod['name']} on {pod['node']} (IP: {pod['ip']}) Status: {pod['status']}")
            if pod["status"] == "Terminating":
                log(f"Delete terminating Worker Pods: {pod['name']}")
                log(f"  {pod['name']} on {pod['node']} (IP: {pod['ip']}) Status: {pod['status']}")
                delete_pod(pod["name"])

        for pod in worker_pods:
            if pod["node"] in not_ready_nodes:
                log(f"Pod {pod['name']} is on NotReady node {pod['node']}, deleting it.")
                worker_id = get_worker_id(pod["ip"])
                if worker_id:
                    delete_worker_from_etcd(worker_id)

                delete_pod(pod["name"])


        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
