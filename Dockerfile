# Dockerfile for yosys synthesis cosimulation test suite
#

FROM debian:buster-slim

RUN apt-get update --allow-releaseinfo-change ; \
	apt-get install -y make git wget bzip2 \
	python3-distutils python3-pytest \
	screen gnupg sudo pkg-config autoconf libtool iverilog


RUN wget -qO - https://section5.ch/section5-apt.key | apt-key add - 
RUN echo "deb http://section5.ch/debian buster non-free" > /etc/apt/sources.list.d/section5.list

RUN apt-get update ; \
	apt-get install -y yosys-pyosys

RUN useradd -u 1000 -g 100 -m -s /bin/bash pyosys 

RUN adduser pyosys sudo
RUN echo "pyosys ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/pyosys-nopw

USER pyosys
RUN install -d /home/pyosys/scripts/recipes
RUN wget https://raw.githubusercontent.com/hackfin/myhdl/upgrade/scripts/recipes/myhdl.mk -O /home/pyosys/scripts/recipes/myhdl.mk
WORKDIR /home/pyosys

