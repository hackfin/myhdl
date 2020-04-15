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

	@always_comb
	def work_a() :
		port_a.next = ROM[addr]

	@always_comb
	def work_b() :
		port_b.next = ROM[~addr]

	@always_comb
	def assign():
		dout.next = port_a ^ port_b

	return instances()


@block
def RomBench(rom):

	dout = Signal(intbv(0)[8:])
	addr = Signal(intbv(1)[8:])
	clk = Signal(bool(0))

	rom_inst = rom(addr, dout)

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

@block
def RomBenchDP(rom):

	dout = Signal(intbv(0)[8:])
	addr = Signal(intbv(1)[8:])
	clk = Signal(bool(0))

	rom_inst = rom(addr, dout)

	@instance
	def stimulus():
		for i in range(D):
			addr.next = i
			yield clk.negedge
			yield clk.posedge
			yield delay(1)
			if __debug__:
				assert dout == ROM[i] ^ ROM[~i]
			print(dout)
		raise StopSimulation()

	@instance
	def clkgen():
		clk.next = 1
		while 1:
			yield delay(10)
			clk.next = not clk

	return clkgen, stimulus, rom_inst

############################################################################

class interface:
	def __init__(self):
		self.addr = 3
		self.data = 8

@block
def cosim_bench(uut, bench):
	"""Cosimulation run for test benches that take a block as argument
	"""

	clk = Signal(bool())
	debug0, debug1 = [ Signal(bool()) for i in range(2) ]

	wrapper = CosimObjectWrapper(uut, "addr,dout" )
	inst_uut = bench(wrapper)
	inst_uut = bench(uut)

	return instances()

def isig(l):
	return Signal(intbv()[l:])

def bsig():
	return Signal(bool())

UUT_LIST =  [ (rom1, RomBench), (rom2_dp, RomBenchDP) ]
# UUT_LIST += [ rom2 ]

@pytest.mark.parametrize("uut,bench", UUT_LIST)
def test_memory(uut, bench):
	run_tb(cosim_bench(uut, bench), 2000)

# Currently unsupported:
UUT_LIST_FAIL = [ rom1a ]

@pytest.mark.xfail
@pytest.mark.parametrize("uut", UUT_LIST_FAIL)
def test_memory_fail(uut, args):
	run_tb(cosim_bench(uut), 2000)

