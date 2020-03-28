all:  vlog vcom 

PYTEST ?= py.test-3

ghdl:
	$(PYTEST) --sim ghdl

vlog:
	$(PYTEST) --sim vlog

vcom:
	$(PYTEST) --sim vcom

iverilog:
	$(PYTEST) --sim iverilog

cver:
	$(PYTEST) --sim cver

clean:
	- rm *.o *.out *.v *.vhd *.pyc *~ *.vcd* *.log *_ghdl

gitclean:
	git clean -dfx
