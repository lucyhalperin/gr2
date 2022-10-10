#!/bin/bash

# Setting up pyenv
eval "$(pyenv init --path)"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

pyenv virtualenv 3.6.15 venv
pyenv activate venv 

# Install rllab
# cd /home/lucyh/Documents/ACL/GR2/rllab
# pip3 install -e .
# cd /home/lucyh/Documents/ACL/GR2

# Install multiagent
# cd /home/lucyh/Documents/ACL/GR2/multiagent-particle-envs
# pip3 install -e .
# cd /home/lucyh/Documents/ACL/GR2

# Install requirements
# cd /home/lucyh/Documents/ACL/GR2/gr2/code 
# pip3 install -r requirements.txt
# cd /home/lucyh/Documents/ACL/GR2

# Install maci 
# cd /home/lucyh/Documents/ACL/GR2/gr2/code 
# pip3 install -e .
# cd /home/lucyh/Documents/ACL/GR2

# Run
#python3.6 ./gr2/code/experiment/run_different_agents_gr2.py



