# Calculates a specific chunk using JOB_COMPLETION_INDEX.
# First calculates initial state, then starts a frame loop that calculates Laplacian(next state), and publishes every 500th frame.

# We use Redis Lists to grab boundary rows (to solve the halo exchange / ghost cell problem), then compute and publish back.
# We use Lists("mailbox" apporach) instead of Pub/Sub(potentially publishing when subscribers aren't ready) to prevent deadlock. 

import os
import numpy as np
import schrodinger #imports the Fortran .so file compiled from build stage (which used f2py)
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
    size_n = 40 # Updated to match example's 40x40 grid
    rows_per_worker = size_n // total_jobs
    
    print(f"Starting worker node for Job Index: {job_index}")

    # 1. Use Fortran to compute initial complex-valued wave state
    init_matrix = np.zeros((size_n, size_n), dtype=np.complex128, order='F')
    schrodinger.schrodinger_mod.compute_wave_matrix(init_matrix, 1, 1.0, 1.0)

    # 2. Extract this worker's chunk
    start_row = job_index * rows_per_worker
    end_row = start_row + rows_per_worker
    matrix = np.asfortranarray(init_matrix[start_row:end_row, :].copy())
    
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

        # --- PHASE 3: PAD + EVOLVE IN FORTRAN (heavy lifting) ---
        padded = np.asfortranarray(np.vstack([top_ghost[np.newaxis, :], matrix, bottom_ghost[np.newaxis, :]]))

        is_top = 1 if job_index == 0 else 0
        is_bottom = 1 if job_index == total_jobs - 1 else 0

        # Fortran computes Laplacian + Schrodinger evolution in compiled code
        schrodinger.schrodinger_mod.evolve_step(padded, dt, is_top, is_bottom)

        # --- PHASE 4: STRIP THE GHOST CELLS ---
        matrix = np.asfortranarray(padded[1:-1, :].copy())

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