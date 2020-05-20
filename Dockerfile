FROM hackfin/myhdl_testing:yosys

RUN sudo apt-get update; sudo apt-get install -y python3-pip
RUN sudo pip3 install --no-cache graphviz pydotplus notebook nbwavedrom

# Check out specific build recipe:
# RUN wget https://raw.githubusercontent.com/hackfin/myhdl/jupyosys/scripts/recipes/myhdl.mk -O /home/pyosys/scripts/recipes/myhdl_yosys.mk


COPY . /home/pyosys/src/myhdl/myhdl-yosys/

RUN jupyter nbextension install \
	/home/pyosys/src/myhdl/myhdl-yosys/example/ipynb/js/ml.js --user && \
	jupyter nbextension enable ml

RUN sudo chown -R pyosys /home/pyosys

RUN ls -R /home/pyosys

RUN make -f /home/pyosys/src/myhdl/myhdl-yosys/scripts/recipes/myhdl.mk all
# RUN cd src/myhdl/myhdl-yosys/ && git checkout jupyosys
