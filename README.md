## Project Overview

This project simulates the evolution of a quantum wave function (via the Schrödinger equation) using a distributed cloud computing architecture. The computationally heavy mathematics are written in Fortran and wrapped in Python using `f2py`. To achieve high performance, the simulation is containerized using Docker and deployed to an **AWS EKS (Kubernetes)** cluster as a parallelized indexed job.

Each Kubernetes Pod calculates a specific "chunk" of the total matrix and publishes the results to an **AWS EC2 Redis broker** via Pub/Sub. A local Python listener subscribes to this broker, stitches the calculated chunks back together in real-time, and renders the final wave interference pattern using **Matplotlib**. The cluster's CPU and resource metrics are actively monitored using a **Prometheus and Grafana** observability stack.

## Video Demo

[![Video demo](https://img.youtube.com/vi/MZqouSv1JUY/0.jpg)](https://youtu.be/MZqouSv1JUY)

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

### 1. The Kubernetes "Sidecar Trap"

* **The Problem:** To fulfill the observability requirements, an `nginx-exporter` container was deployed alongside the Fortran compute engine in the same Pod (the Sidecar Pattern). However, because the exporter is a continuous web server, it prevented the Kubernetes batch Job from ever entering a `Completed` state when the math finished, permanently deadlocking the cluster's parallel execution.
* **The Workaround:** Implemented Kubernetes' new **Native Sidecar** feature. By moving the `nginx-exporter` into the `initContainers` block and assigning it a `restartPolicy: Always`, Kubernetes successfully treats it as a background service and automatically terminates it the moment the primary Fortran worker completes its calculation.

### 2. The Persistent Volume (PV) Dynamic Provisioning Block

* **The Problem:** Modern AWS EKS clusters no longer automatically provision EBS (Elastic Block Store) hard drives for Persistent Volume Claims (PVCs) without explicitly configuring complex IAM roles and installing the EBS CSI Driver plugin. This left the PVCs stuck in a `Pending` state.
* **The Workaround:** Bypassed the need for dynamic cloud storage by explicitly defining a manual `PersistentVolume` that uses `hostPath`. This maps the storage directly to the EC2 worker node's local disk (`/mnt/wave-data`), satisfying the persistent storage requirement while ensuring the pods instantly bind and spin up.

### 3. Fortran Compilation Declaration Error

* **The Problem:** During the `f2py` Docker build stage, the Fortran compiler threw a strict declaration order error regarding the variables in the subroutine. Fortran enforces rigid rules where variable types must be declared before any executable statements or implicit typing overrides.
* **The Workaround:** Reordered the variable declarations inside `schrodinger.f90`, explicitly defining the `intent(in)` and `intent(inout)` parameters at the very top of the module before any execution logic, ensuring a flawless multi-stage Docker compilation.

## How to Run

1. **Build and Push the Container:**
```bash
docker build -t wave-worker .
docker tag wave-worker:latest <AWS_ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/wave-worker:latest
docker push <AWS_ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/wave-worker:latest

```


2. **Start the Local Listener:**
Ensure `redis`, `numpy`, and `matplotlib` are installed locally, then start the visualization subscriber:
```bash
python visualize.py

```


3. **Deploy the Kubernetes Job:**
Apply the infrastructure configuration to your EKS cluster to begin parallel computation:
```bash
kubectl apply -f job-deployment.yaml

```