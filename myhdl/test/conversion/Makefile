.PHONY: all general toVerilog2 toVHDL toVerilog toYosys

all: general toVerilog2 toVHDL toVerilog toYosys

general:
	cd $@; py.test --sim ghdl; py.test --sim iverilog 

toVerilog2:
	cd $@; py.test --sim iverilog 

toVHDL:
	cd $@; py.test --sim ghdl 

toYosys:
	cd $@; py.test-3 --sim iverilog 

toVerilog: 
	cd $@; py.test --sim iverilog 

gitclean:
	git clean -dfx    
    
