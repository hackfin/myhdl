.PHONY: all general toVerilog2 toVHDL toVerilog toYosys

PYTEST ?= py.test
PYTEST3 ?= py.test-3

all: general toVerilog2 toVHDL toVerilog toYosys

general:
	cd $@; $(PYTEST) --sim ghdl; $(PYTEST) --sim iverilog 

toVerilog2:
	cd $@; $(PYTEST) --sim iverilog 

toVHDL:
	cd $@; $(PYTEST) --sim ghdl 

toYosys:
	cd $@; $(PYTEST3)

toVerilog: 
	cd $@; $(PYTEST) --sim iverilog 

gitclean:
	git clean -dfx    
    
