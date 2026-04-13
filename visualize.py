# this file listens to Redis for chunks generated from workers.
# when a full frame of 10 chunks are received, plot it and wait for next frame

import redis
import json
import numpy as np
import matplotlib.pyplot as plt

def main():
    # 1. Connect to your EC2 Redis Broker
    r = redis.Redis(
        host='<YOUR_EC2_PUBLIC_IP>', # Your EC2 Public IP
        port=6379,
        decode_responses=True
    )

    # 2. Setup Matplotlib 3D (taken from schrodinger.py example file)
    plt.ion()
    fig = plt.figure(figsize=(8, 6))
    ax = fig.add_subplot(111, projection='3d')
    try:
        ax.set_box_aspect(None, zoom=1.2) 
    except Exception:
        ax.dist = 6 

    title_text = fig.suptitle("Schrödinger Wave", fontsize=14, y=0.95)
    fig.subplots_adjust(left=0.0, right=1.0, bottom=0.0, top=0.95)

    # Setup the grid coordinates
    N = 40
    x = np.linspace(-4, 4, N)
    y = np.linspace(-2, 2, N)
    X, Y = np.meshgrid(x, y)

    # 3. Setup Redis Listener
    pubsub = r.pubsub()
    pubsub.subscribe('wave_channel')
    print("Listening for live 3D wave frames...")

    # 4. The Frame Buffer
    frame_buffer = {}
    total_jobs = 10
    rows_per_worker = N // total_jobs

    for message in pubsub.listen():
        if message['type'] == 'message':
            payload = json.loads(message['data'])
            frame = payload['frame']
            job_index = payload['job_index']
            chunk_data = np.array(payload['chunk_data'])

            # Create a holding pen for this frame if it doesn't exist
            if frame not in frame_buffer:
                frame_buffer[frame] = {}

            # Store the chunk
            frame_buffer[frame][job_index] = chunk_data

            # Check if we successfully caught all 10 chunks for this specific frame
            if len(frame_buffer[frame]) == total_jobs:
                
                # Assemble the master matrix
                full_matrix = np.zeros((N, N))
                for j in range(total_jobs):
                    start_row = j * rows_per_worker
                    end_row = start_row + rows_per_worker
                    full_matrix[start_row:end_row, :] = frame_buffer[frame][j]

                # --- DRAW THE FRAME ---
                ax.clear()
                
                # Square the magnitude to get the probability density (like the prof did)
                magnitude_squared = full_matrix**2
                
                surf = ax.plot_surface(X, Y, magnitude_squared, cmap='jet', vmin=0, vmax=1)
                ax.set_zlim(0, 1)
                title_text.set_text(f"Schrödinger Wave - Frame {frame}")
                ax.axis('off')
                
                plt.pause(0.01)

                # --- CLEANUP ---
                # Delete the frame from memory now that it is drawn
                del frame_buffer[frame]
                
                # Garbage collection: delete any severely lagging orphaned frames
                for old_frame in list(frame_buffer.keys()):
                    if old_frame < frame - 500:
                        del frame_buffer[old_frame]

if __name__ == "__main__":
    main()