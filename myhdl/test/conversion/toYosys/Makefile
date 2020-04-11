all: yosys

yosys:
	py.test-3

failures:
	py.test-3 _test_fail.py

clean:
	- rm *.o *.out *.v *.vhd *.pyc *~ *.vcd* *.log *_ghdl

gitclean:
	git clean -dfx
