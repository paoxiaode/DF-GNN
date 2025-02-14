set -e
docker build . -t dfgnn:latest
docker stop dfgnn
docker run --rm --gpus all --cap-add sys_ptrace --name dfgnn --entrypoint /bin/bash --ipc=host --ulimit memlock=-1 --cap-add=SYS_ADMIN --ulimit stack=67108864 -itd -v /home/ubuntu/code:/workspace2 dfgnn:latest
docker exec -it dfgnn bash
