# Memory tests of various sorts
#
# - ROM test: TODO: Check inference to primitives and simulate full chain
#
#

import myhdl
from myhdl import *
from .cosim_common import *
from .lfsr8 import lfsr8
from random import randrange
import pytest
from myhdl.conversion import yshelper

D = 256

ROM = tuple([randrange(D) for i in range(D)])

@block
def rom1(addr, dout):
	"Asynchronous ROM inference"

	@always_comb
	def worker() :
		dout.next = ROM[addr]

	return instances()

@block
def rom1a(addr, dout):
	"Above variant with explicit integer indexing"

	@always_comb
	def worker() :
		dout.next = ROM[int(addr)]

	return instances()

@block
def rom2(clk, addr, dout):
	"Synchronous variant"

	@always(clk.posedge)
	def worker() :
		dout.next = ROM[addr]

	return instances()


@block
def rom2_dp(addr, dout):
	"""Synchronous variant, dual ported
	Is expected to infer one memory initialization, several read ports"""

	port_a, port_b = [ Signal(modbv(0)[len(dout):]) for i in range(2) ]
	ROM2 = tuple([randrange(256) for i in range(256)])

	@always_comb
	def work_a() :
		port_a.next = ROM2[addr]

	@always_comb
	def work_b() :
		port_b.next = ROM2[~addr]

	@always_comb
	def assign():
		dout.next = port_a ^ port_b

	return instances()


@block
def RomBench(rom):

	dout = Signal(intbv(0)[8:])
	addr = Signal(intbv(1)[8:])
	clk = Signal(bool(0))

	rom_inst = rom(dout, addr, clk)

	@instance
	def stimulus():
		for i in range(D):
			addr.next = i
			yield clk.negedge
			yield clk.posedge
			yield delay(1)
			if __debug__:
				assert dout == ROM[i]
			print(dout)
		raise StopSimulation()

	@instance
	def clkgen():
		clk.next = 1
		while 1:
			yield delay(10)
			clk.next = not clk

	return clkgen, stimulus, rom_inst

# Note: Don't share signal instances, otherwise driver collisons!

def isig(l):
	return Signal(intbv()[l:])

def bsig():
	return Signal(bool())

UUT_LIST =  [ ( rom1,    (isig(8), isig(8)) ) ]
UUT_LIST += [ ( rom2_dp, (isig(8), isig(8)) ) ]
UUT_LIST += [ ( rom2,    (bsig(), isig(8), isig(8)) ) ]

@pytest.mark.parametrize("uut, args", UUT_LIST)
def test_memory(uut, args):
	arst = False
	name = uut.func.__name__
	design = yshelper.Design(name)
	inst_uut = uut(*args)
	inst_uut.convert("yosys_module", design, name=name, trace=False)
	design.write_verilog(name, True)
	# run_tb(cosim_bench(uut, args), 2000)



# Currently unsupported:
UUT_LIST_FAIL = [ ( rom1a, (isig(8), isig(8)) ) ]

@pytest.mark.xfail
@pytest.mark.parametrize("uut, args", UUT_LIST_FAIL)
def test_memory_fail(uut, args):
	arst = False
	name = uut.func.__name__
	design = yshelper.Design(name)
	inst_uut = uut(*args)
	inst_uut.convert("yosys_module", design, name=name, trace=False)
	design.write_verilog(name, True)
	# run_tb(cosim_bench(uut, args), 2000)

