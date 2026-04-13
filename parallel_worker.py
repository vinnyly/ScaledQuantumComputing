# calculates a specific chunk using JOB_COMPLETION_INDEX.
# also grabs boundary rows from Redis Lists (to solve the halo exchange / ghost cell problem), then compute and publish back

import os
import numpy as np
import schrodinger #imports the Fortran .so file compiled from build stage
import redis
import json

r = redis.Redis(
    host='<YOUR_EC2_PUBLIC_IP>', #public EC2 IP
    port=6379,
    decode_responses=True
)

def main():
    job_index = int(os.environ.get('JOB_COMPLETION_INDEX', '0'))
    total_jobs = 10
    size_n = 40 # Updated to match professor's 40x40 grid
    rows_per_worker = size_n // total_jobs
    
    print(f"Starting worker node for Job Index: {job_index}")

    # 1. Use legacy Fortran to compute initial real-valued wave state (untouched)
    init_matrix = np.zeros((size_n, size_n), dtype=np.float64, order='F')
    schrodinger.schrodinger_mod.compute_wave_matrix(init_matrix, 1, 1.0, 1.0)

    # 2. Extract this worker's chunk and convert to complex for quantum evolution
    # Fortran handles the real-valued initial state; Python handles complex time evolution
    start_row = job_index * rows_per_worker
    end_row = start_row + rows_per_worker
    matrix = init_matrix[start_row:end_row, :].astype(np.complex128)
    
    # Inject initial state (only Worker 5 has the center of the grid!)
    if job_index == total_jobs // 2:
        matrix[rows_per_worker//2, size_n//2] = 1.0 + 0j 
        
    dt = 0.0005

    # 3. THE ANIMATION LOOP
    for frame in range(10000):
        
        # --- PHASE 1: SEND BOUNDARIES (Drop in mailboxes) ---
        if job_index > 0:
            # Send my top row to the worker above me (preserve complex values)
            row = matrix[0, :]
            r.rpush(f"frame:{frame}:job:{job_index-1}:bottom",
                    json.dumps({"re": row.real.tolist(), "im": row.imag.tolist()}))
        
        if job_index < total_jobs - 1:
            # Send my bottom row to the worker below me
            row = matrix[-1, :]
            r.rpush(f"frame:{frame}:job:{job_index+1}:top",
                    json.dumps({"re": row.real.tolist(), "im": row.imag.tolist()}))

        # --- PHASE 2: RECEIVE BOUNDARIES (Check mailboxes) ---
        # Default to walls of 0 for the absolute top and bottom of the whole grid
        top_ghost = np.zeros(size_n, dtype=np.complex128)
        bottom_ghost = np.zeros(size_n, dtype=np.complex128)

        if job_index > 0:
            # Wait for the worker above to send their bottom row
            _, data = r.blpop(f"frame:{frame}:job:{job_index}:top", timeout=0)
            d = json.loads(data)
            top_ghost = np.array(d["re"]) + 1j * np.array(d["im"])
            
        if job_index < total_jobs - 1:
            # Wait for the worker below to send their top row
            _, data = r.blpop(f"frame:{frame}:job:{job_index}:bottom", timeout=0)
            d = json.loads(data)
            bottom_ghost = np.array(d["re"]) + 1j * np.array(d["im"])

        # --- PHASE 3: COMPUTE LAPLACIAN (Python handles complex math, not Fortran) ---
        padded = np.vstack([top_ghost[np.newaxis, :], matrix, bottom_ghost[np.newaxis, :]])

        up = padded[:-2, :]
        down = padded[2:, :]
        left = np.roll(matrix, 1, axis=1)
        right = np.roll(matrix, -1, axis=1)

        laplacian = up + down + left + right - 4 * matrix

        # Boundary conditions (walls)
        laplacian[:, 0] = 0
        laplacian[:, -1] = 0
        if job_index == 0:
            laplacian[0, :] = 0
        if job_index == total_jobs - 1:
            laplacian[-1, :] = 0

        # --- PHASE 4: EVOLVE SCHRÖDINGER EQUATION ---
        # The 1j is the imaginary unit — this is what makes it a quantum wave, not heat diffusion
        matrix += 1j * laplacian * dt

        # --- PHASE 5: PUBLISH TO LAPTOP ---
        # We only send every 500th frame over the network to prevent lagging
        if frame % 500 == 0:
            payload = {
                "frame": frame,
                "job_index": job_index,
                "chunk_data": np.abs(matrix).tolist() # Send magnitude for plotting
            }
            r.publish('wave_channel', json.dumps(payload))
            print(f"Frame {frame} published.")

if __name__ == "__main__":
    main()