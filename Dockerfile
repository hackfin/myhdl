FROM hackfin/myhdl_testing:yosys

RUN sudo apt-get update; sudo apt-get install -y python3-pip
RUN sudo pip3 install --no-cache graphviz notebook

# Check out specific build recipe:
RUN wget https://raw.githubusercontent.com/hackfin/myhdl/jupyosys/scripts/recipes/myhdl.mk -O /home/pyosys/scripts/recipes/myhdl_yosys.mk

RUN make -f scripts/recipes/myhdl_yosys.mk all
RUN cd src/myhdl/myhdl-yosys/ && git checkout jupyosys
