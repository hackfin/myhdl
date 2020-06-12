# Memory tests of various sorts
#
# - ROM test: TODO: Check inference to primitives and simulate full chain
#
#

import myhdl
from myhdl import *
from .cosim_common import *
from .lfsr8 import lfsr8
from random import randrange, seed
import pytest
from myhdl.conversion import yshelper

from .test_simple import up_counter

# Yosys blackbox RAM library
import sys
sys.path.append("../../../../synthesis/yosys")
import ram

D = 256

ROM = tuple([randrange(D) for i in range(D)])

@block
def rom1(clk, addr, dout):
	"Asynchronous ROM inference"

	@always_comb
	def worker() :
		dout.next = ROM[addr]

	return instances()

@block
def rom1a(clk, addr, dout):
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
def rom2_dp(clk, addr, dout):
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

	rom_inst = rom(clk, addr, dout)

	@instance
	def stimulus():
		for i in range(D):
			addr.next = i
			yield clk.negedge
			yield clk.posedge
			yield delay(1)
			print("inst:%s VALUES[%d]" % (rom.name, i), int(dout), hex(ROM[i]))
			if __debug__:
				assert dout == ROM[i]
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

	rom_inst = rom(clk, addr, dout)

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

@block
def tb_memory(memory, unitname):

	a0, a1, b0, b1 = [ ram.RAMport(8, 8) for i in range(4) ]
	clk = Signal(bool(0))

	@block
	def dpram_mapped(unitname, \
			a_clk, a_ce, a_we, a_addr, a_read, a_write, a_sel, \
			b_clk, b_ce, b_we, b_addr, b_read, b_write, b_sel, \
		 HEXFILE = None, USE_CE = False):
		"Wrapper for cosimulation object"
		args = locals()
		name = unitname + "_mapped"
		args.pop("unitname")
		return setupCosimulation(name, use_assert=False, interface=args, debug=False)
  
	ram_inst = memory(a0, b0, None, False)
	ram_inst_uut = dpram_mapped(unitname,
		a1.clk, a1.ce, a1.we, a1.addr, a1.read, a1.write, a1.sel, \
		b1.clk, b1.ce, b1.we, b1.addr, b1.read, b1.write, b1.sel, \
		None, False)


	@instance
	def stimulus():
		a0.ce.next = True
		a1.ce.next = True
		b0.ce.next = True
		b1.ce.next = True
		seed(20)

		for i in range(256):
			a1.addr.next = i
			a0.addr.next = i
			v = randrange(0, 256)
			a0.write.next = v
			a1.write.next = v
			yield clk.negedge
			a0.we.next = True
			a1.we.next = True
			yield clk.posedge

			yield clk.negedge

			a0.we.next = False
			a1.we.next = False

			b0.addr.next = i
			b1.addr.next = i

			yield clk.posedge
			yield clk.negedge

			print("VALUES[%d]" % (i), b0.read, b1.read)
			if __debug__:
				if b0.read != b1.read:
					for i in range(3):
						yield clk.posedge

					raise ValueError("Simulation mismatch")
			prev = i
		raise StopSimulation()

	@always_comb
	def assign():
		a0.clk.next = clk
		a1.clk.next = clk
		b0.clk.next = clk
		b1.clk.next = clk
		
	@instance
	def clkgen():
		clk.next = 1
		while 1:
			yield delay(1)
			clk.next = not clk

	return instances()


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

	wrapper = CosimObjectWrapper(uut, "clk,addr,dout")
	wrapper.trace = True # Trace
	wrapper.synth_pass = True # Run a synthesis pass
	inst_uut1 = bench(wrapper)
	inst_uut2 = bench(uut)

	return instances()

def isig(l):
	return Signal(intbv()[l:])

def bsig():
	return Signal(bool())

UUT_LIST =	[ (rom1, RomBench), (rom1a, RomBench), (rom2_dp, RomBenchDP) ]
UUT_LIST += [ (rom2, RomBench) ]

@pytest.mark.parametrize("uut,bench", UUT_LIST)
def test_memory(uut, bench):
	run_tb(cosim_bench(uut, bench), 2000)

def test_ram():
	"""RAM unit test"""
	def convert(unit):
		a, b = [ ram.RAMport(8, 8) for i in range(2) ]

		dpram = unit(a, b, None, True)

		design = yshelper.Design("dpram")

		dpram.convert("yosys_module", design, name="dpram", trace=True)

		return design
	ram_design = convert(ram.dpram_r1w1)

	ram_design.test_synth()
	ram_design.write_verilog(ram_design.name, True)
	tb = tb_memory(ram.dpram_r1w1, ram_design.name)
	tb.config_sim(backend = 'myhdl', timescale="1ps", trace=True)
	tb.run_sim()
	tb.quit_sim()



# Currently unsupported:
UUT_LIST_FAIL = [ ]

@pytest.mark.xfail
@pytest.mark.parametrize("uut,bench", UUT_LIST_FAIL)
def test_memory_fail(uut, bench):
	run_tb(cosim_bench(uut, bench), 2000)

