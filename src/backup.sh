#!/bin/bash
# while true
# do
#     docker cp thirsty_golick:"/examples/ldc/" "simnet/ldc_10mps_new_${i}/" &
#     sleep $((2*60)) 
#     # kill "$!"
#     i=$((i+1))
# done
while true
do
    steps=$(cat /examples/ldc/network_checkpoint_ldc_2d/checkpoint | grep model_checkpoint_path: | grep -Eo '[0-9]*')
    # echo "steps: ${steps}"
    # convert steps to integer
    steps=$(($steps))
    # check if steps is divisible by 20000
    if [ $(($steps % 20000)) -eq 0 ]; then
        echo "20000 steps done. Backing up files..."
        # backup files
        echo "Copying checkpoint at ${steps}..."
        cp -r "~/simnet/examples/ldc/network_checkpoint_ldc_2d/train_domain/" "~/simnet/results/train_domain_${steps}"
        i=$((i+1))
    fi
done