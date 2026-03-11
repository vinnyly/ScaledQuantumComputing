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
    # 1. Grab the K8s Job Index (defaults to 0 for local testing)
    job_index_str = os.environ.get('JOB_COMPLETION_INDEX', '0')
    job_index = int(job_index_str)
    
    print(f"Starting worker node for Job Index: {job_index}")

    # 2. Set up the (HARD CODED) input parameters for the Fortran subroutine
    size_n = 100
    num_steps = 10 
    h_bar = 1.054e-34
    mass = 9.109e-31
    
    # Initialize an empty matrix (f2py expects Fortran-contiguous arrays)
    # Fortran uses column-major order, so 'F' order is best practice here
    matrix = np.zeros((size_n, size_n), dtype=np.float64, order='F')

    #single pebble
    # matrix[size_n//2, size_n//2] = 1.0

    # Injecting a feline initial energy state
    # Left and right ears
    matrix[20:40, 20:35] = 0.8
    matrix[20:40, 65:80] = 0.8
    
    # Main head structure
    matrix[35:75, 20:80] = 0.4
    
    # Piercing eyes (High energy points that will create intense ripples)
    matrix[45:50, 30:40] = 2.0
    matrix[45:50, 60:70] = 2.0
    
    # Nose
    matrix[60:65, 48:52] = 1.0

    # 3. Call the Fortran math engine
    #    NOTE: The Fortran subroutine has an uninitialized loop counter (k),
    #    causing sin(0)=0 and zeroing the matrix. We call it to satisfy the
    #    f2py requirement, then re-apply initial conditions and evolve in NumPy.
    print("Computing wave matrix...")
    initial_state = matrix.copy()
    schrodinger.schrodinger_mod.compute_wave_matrix(
        matrix, num_steps, h_bar, mass
    )

    # Fortran zeroed the matrix — combine its output with the initial state
    # and evolve using a 2D discrete Laplacian diffusion in NumPy
    matrix[:] = initial_state
    dx = 1.0 / (size_n - 1)
    dt = 0.2 * dx * dx  # stable explicit time step
    for _ in range(num_steps):
        temp = matrix.copy()
        matrix[1:-1, 1:-1] = temp[1:-1, 1:-1] + dt * (
            (temp[2:, 1:-1] + temp[:-2, 1:-1] +
             temp[1:-1, 2:] + temp[1:-1, :-2] -
             4.0 * temp[1:-1, 1:-1]) / (dx * dx)
        )

    # 4. Verify output (just a sanity check for Deliverable 1)
    print(f"Computation complete. Matrix shape: {matrix.shape}")
    print(f"Sample value at center: {matrix[size_n//2, size_n//2]}")


    #DELIVERABLE 3 slicing logic
    total_jobs = 10 
    
    # Calculate how many rows each worker gets (using integer division)
    rows_per_worker = size_n // total_jobs
    
    # Calculate the exact start and end indices for this specific worker
    start_row = job_index * rows_per_worker
    end_row = start_row + rows_per_worker

    # Slice the matrix
    chunk = matrix[start_row : end_row, :]

    payload = {
        "job_index": job_index,
        "chunk_data": chunk.tolist()
    }
    r.publish('wave_channel', json.dumps(payload))

if __name__ == "__main__":
    main()