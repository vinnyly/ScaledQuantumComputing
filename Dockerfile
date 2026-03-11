#instructions for docker to build images. build one for each stage

#builder environment
FROM python:3.11-slim AS builder
RUN apt-get update && apt-get install -y gfortran
RUN pip install numpy
WORKDIR /build
COPY schrodinger.f90 .
RUN python -m numpy.f2py -c -m schrodinger schrodinger.f90

#runtime environment
FROM python:3.11-slim
WORKDIR /app
RUN pip install numpy && pip install redis
COPY --from=builder /build/*.so .
COPY parallel_worker.py .
#set default for env var
ENV JOB_COMPLETION_INDEX=0
CMD ["python", "parallel_worker.py"]