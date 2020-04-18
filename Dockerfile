FROM hackfin/myhdl_testing:yosys

RUN sudo apt-get update; sudo apt-get install -y python3-pip
RUN sudo pip3 install --no-cache graphviz notebook

RUN make -f scripts/recipes/myhdl.mk all
RUN cd src/myhdl/myhdl-yosys/ && git checkout jupyosys
