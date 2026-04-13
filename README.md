# Scaled Quantum Computing - Schrödinger Waves

<img width="415" height="305" alt="image" src="https://github.com/user-attachments/assets/e122d493-6aab-4e92-880c-b8f0e1c51316" />
<img width="415" height="305" alt="image" src="https://github.com/user-attachments/assets/54f34f09-4463-422c-9d0c-c2bb6ba83233" />

## Project Overview

This project simulates the evolution of a quantum wave function (the Schrödinger equation) using a distributed cloud computing architecture.

The computationally heavy mathematics are written in Fortran and wrapped in Python using `f2py`. To achieve high performance, the simulation is containerized using Docker and deployed to an **AWS EKS (Kubernetes)** cluster as a parallelized indexed job.

Each Kubernetes Pod calculates a specific "chunk" of the total matrix and publishes the results to an **AWS EC2 Redis broker** via Pub/Sub. Workers syncronize boundary rows via **Redis Lists**.

A local Python listener subscribes to this broker, stitches the calculated chunks back together in real-time, and renders the final wave interference pattern using **Matplotlib**. The cluster's CPU and resource metrics are actively monitored using a **Prometheus and Grafana** observability stack.


## Architecture Diagram

![arch drawio](https://github.com/user-attachments/assets/96414142-5918-49d9-a88c-848cc220498b)

## Tech Stack & Architecture

* **Compute Engine:** Fortran (`schrodinger.f90`), Python, NumPy, `f2py`
* **Containerization:** Docker (Multi-stage builds), AWS ECR
* **Orchestration:** Kubernetes (AWS EKS), Helm
* **Messaging / Broker:** Redis (Hosted on AWS EC2)
* **Observability:** Prometheus, Grafana, Nginx-Prometheus-Exporter (Sidecar Pattern)
* **Visualization:** Python, Matplotlib

## Architectural Decisions & Workarounds

Building a distributed cloud system often requires engineering around strict environment constraints. Below are the key roadblocks encountered during development and the architectural workarounds implemented to solve them:

### 1. Solving the Ghost Cell Boundary Synchronization Problem
* **The Problem:** When the 40×40 grid is split across 10 parallel workers, each worker needs to know its neighbor's boundary rows to correctly compute the Laplacian at its edges. Without these "ghost cells," the math produces incorrect results at chunk boundaries.
* **The Workaround:** Implemented a halo exchange pattern using **Redis Lists** (`rpush`/`blpop`). Each frame, workers push their boundary rows to their neighbors' "mailboxes" and block-wait for their own. Redis Lists were chosen over Pub/Sub to guarantee delivery and prevent race conditions, since workers must synchronize before computing each frame.

### 2. The Kubernetes "Sidecar Trap"

* **The Problem:** To fulfill the observability requirements, an `nginx-exporter` container was deployed alongside the Fortran compute engine in the same Pod (the Sidecar Pattern). However, because the exporter is a continuous web server, it prevented the Kubernetes batch Job from ever entering a `Completed` state when the math finished, permanently deadlocking the cluster's parallel execution.
* **The Workaround:** Implemented Kubernetes' new **Native Sidecar** feature. By moving the `nginx-exporter` into the `initContainers` block and assigning it a `restartPolicy: Always`, Kubernetes successfully treats it as a background service and automatically terminates it the moment the primary Fortran worker completes its calculation.

### 3. The Persistent Volume (PV) Dynamic Provisioning Block

* **The Problem:** Modern AWS EKS clusters no longer automatically provision EBS (Elastic Block Store) hard drives for Persistent Volume Claims (PVCs) without explicitly configuring complex IAM roles and installing the EBS CSI Driver plugin. This left the PVCs stuck in a `Pending` state.
* **The Workaround:** Bypassed the need for dynamic cloud storage by explicitly defining a manual `PersistentVolume` that uses `hostPath`. This maps the storage directly to the EC2 worker node's local disk (`/mnt/wave-data`), satisfying the persistent storage requirement while ensuring the pods instantly bind and spin up.

## How to Run

### Prerequisites
* An AWS account with active credits
* AWS CLI (configured with credentials)
* Docker
* kubectl
* Helm (for Prometheus/Grafana observability stack)
* Python 3+ with `pip`
* A running AWS EKS cluster
* An AWS ECR repository

Replace the following placeholders in the source files with your own values before building or running:

| Placeholder | File(s) | Replace With |
|---|---|---|
| `<YOUR_AWS_ACCOUNT_ID>` | `job-deployment.yaml` | Your 12-digit AWS account ID |
| `<YOUR_EC2_PUBLIC_IP>` | `parallel_worker.py`, `visualize.py` | The public IP of your EC2 Redis instance |

### 0. Set Up the Redis Broker (EC2)

Launch an EC2 instance and install Redis:
```bash
sudo apt-get update && sudo apt-get install -y redis-server
```
Edit `/etc/redis/redis.conf` to allow external connections:
```
bind 0.0.0.0
protected-mode no
```
Then restart Redis:
```bash
sudo systemctl restart redis-server
```
Ensure the EC2 security group allows inbound traffic on **port 6379**.

### 1. Build and Push the Container
```bash
docker build -t wave-worker .
docker tag wave-worker:latest <YOUR_AWS_ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com/wave-worker:latest
docker push <YOUR_AWS_ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com/wave-worker:latest
```

### 2. Install Local Dependencies and Start the Listener
```bash
pip install redis numpy matplotlib
python visualize.py
```

### 3. Deploy the Kubernetes Job

Apply the infrastructure configuration to your EKS cluster to begin parallel computation:
```bash
kubectl apply -f job-deployment.yaml
```